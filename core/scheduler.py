# core/scheduler.py

from datetime import datetime, timedelta, timezone

from skyfield.api import load

from satellites.satellites import (
    get_selected_satellites,
    get_satellite_band,
)

from core.visibility import calculate_visibility
from core.scoring import calculate_score


# ==========================================================
# Skyfield Timescale
# ==========================================================

ts = load.timescale()
MINIMUM_PASS_DURATION_MINUTES = 10


# ==========================================================
# Finds the first mutual visibility time for a satellite
# ==========================================================

def find_earliest_mutual_visibility(
    satellite,
    goddard,
    mission_site,
    start_time,
    event_time,
):
    """
    Finds the first time before the mission event
    when the satellite is mutually visible from
    both Goddard and the mission site.

    Returns:
        datetime:
            First mutual visibility time.

        None:
            If no mutual visibility occurs.
    """

    check_time = start_time

    while check_time < event_time:

        skyfield_time = ts.from_datetime(check_time)

        goddard_view = calculate_visibility(
            satellite,
            goddard,
            skyfield_time,
            observer_name="Goddard",
        )

        mission_view = calculate_visibility(
            satellite,
            mission_site,
            skyfield_time,
            observer_name="Mission Site",
        )

        if (
            goddard_view["visible"]
            and mission_view["visible"]
        ):
            return check_time

        check_time += timedelta(minutes=1)

    return None


# ==========================================================
# Determines satellite pre-event priorities
# ==========================================================

def _run_meosar_id(satellite, fallback):
    value = getattr(satellite, "meosar_id", None)
    if value is None:
        identifier = str(satellite.model.satnum).strip()
        value = next((v for k, v in fallback.items() if str(k).strip() == identifier), None)
    return str(value).strip() if value is not None else None


def _fallback_metadata(satellites):
    # Run-loaded objects already carry their immutable ID/band metadata.
    return get_selected_satellites() if any(getattr(s, "meosar_id", None) is None for s in satellites) else {}


def calculate_satellite_priorities(
    satellites,
    goddard,
    mission_site,
    mission,
):
    """
    Determines whether each satellite can establish
    mutual visibility at least 30 minutes before
    the mission event.
    """

    priorities = {}

    start_time = mission.get_start_time()
    event_time = mission.event_time

    required_start_time = (
        event_time - timedelta(minutes=30)
    )

    selected_satellites = _fallback_metadata(satellites)

    for satellite in satellites:

        norad_id = satellite.model.satnum

        meosar_id = _run_meosar_id(satellite, selected_satellites)

        if meosar_id is None:
            continue

        earliest_visibility = (
            find_earliest_mutual_visibility(
                satellite,
                goddard,
                mission_site,
                start_time,
                event_time,
            )
        )

        if earliest_visibility is None:

            priorities[meosar_id] = {
                "qualified": False,
                "earliest_visibility": None,
                "lead_time_minutes": 0,
            }

            continue

        lead_time = (
            event_time - earliest_visibility
        ).total_seconds() / 60

        priorities[meosar_id] = {
            "qualified": (
                earliest_visibility
                <= required_start_time
            ),
            "earliest_visibility": earliest_visibility,
            "lead_time_minutes": lead_time,
        }

    return priorities


# ==========================================================
# Finds the best satellite assignment at one point in time
# ==========================================================

def create_assignment(
    satellites,
    antennas,
    goddard,
    mission_site,
    time,
    current_assignments,
    satellite_priorities,
    strategy=None,
):
    """
    Finds the best assignment for every available antenna.

    Rules:

    1. Satellite must be visible from Goddard.
    2. Satellite must be visible from mission site.
    3. Antenna must support the satellite band.
    4. A satellite may only be tracked by one antenna.
    5. Satellites capable of establishing tracking at least
    30 minutes before the mission event receive priority.
    """

    # Geometry is part of baseline scheduling; alternate coverage remains opt-in.
    strategy = dict(strategy or {})
    strategy["geometry"] = True
    if strategy.get("enabled") is False:
        strategy["locations"] = []

    candidates = []

    selected_satellites = _fallback_metadata(satellites)

    # ======================================================
    # Find all mutually visible satellites
    # ======================================================

    for satellite in satellites:

        norad_id = satellite.model.satnum

        meosar_id = _run_meosar_id(satellite, selected_satellites)

        if meosar_id is None:
            continue

        band = getattr(satellite, "band", None) or get_satellite_band(meosar_id)

        goddard_view = calculate_visibility(
            satellite,
            goddard,
            time,
            observer_name="Goddard",
        )

        mission_view = calculate_visibility(
            satellite,
            mission_site,
            time,
            observer_name="Mission Site",
        )

        # Satellite must be visible from both locations.

        if not goddard_view["visible"]:
            continue

        if not mission_view["visible"]:
            continue

        score = calculate_score(
            goddard_view,
            mission_view,
        )

        priority = satellite_priorities.get(
            meosar_id,
            {
                "qualified": False,
                "earliest_visibility": None,
                "lead_time_minutes": 0,
            },
        )

        alternate_visible=[]
        if strategy:
            for site in strategy.get("locations",[]):
                alternate_visible.append(bool(calculate_visibility(satellite,site["observer"],time,observer_name=site["name"])["visible"]))

        candidates.append(
            {
                "satellite": satellite,
                "norad_id": norad_id,
                "meosar_id": meosar_id,
                "band": band,

                "goddard_elevation":
                    goddard_view["elevation_deg"],

                "mission_elevation":
                    mission_view["elevation_deg"],

                "score": score,
                "mission_azimuth": float(mission_view.get("azimuth_deg",0)),
                "alternate_visible": alternate_visible,

                "qualified":
                    priority["qualified"],

                "earliest_visibility":
                    priority["earliest_visibility"],

                "lead_time_minutes":
                    priority["lead_time_minutes"],
            }
        )

    # ======================================================
    # Sort candidates by priority
    #
    # 1. Qualified for 30-minute pre-event tracking
    # 2. Greatest lead time
    # 3. Highest visibility score
    # ======================================================

    candidates.sort(
        key=lambda candidate: (
            candidate["qualified"],
            candidate["lead_time_minutes"],
            candidate["score"],
        ),
        reverse=True,
    )

    # ======================================================
    # Debug output
    # ======================================================

    print()
    print("MUTUALLY VISIBLE SATELLITES")
    print("============================")

    for candidate in candidates:

        print(
            "  ",
            candidate["meosar_id"],
            "| Score:",
            round(candidate["score"], 2),
            "| Band:",
            candidate["band"],
            "| Qualified:",
            candidate["qualified"],
            "| Lead:",
            round(
                candidate["lead_time_minutes"],
                1,
            ),
            "min",
        )

    # ======================================================
    # Assign satellites
    # ======================================================

    assignments = {}
    used_satellites = set()

    # ======================================================
    # Preserve existing assignments when possible
    # ======================================================

    for antenna_name, assignment in (
        current_assignments.items()
    ):

        meosar_id = str(assignment["meosar_id"])
        if meosar_id in used_satellites:
            continue

        for candidate in candidates:

            if candidate["meosar_id"] != meosar_id:
                continue

            antenna_data = antennas.get(
                antenna_name
            )

            if antenna_data is None:
                break

            if (
                antenna_data["operational"]
                and candidate["band"]
                in antenna_data["bands"]
            ):

                assignments[
                    antenna_name
                ] = candidate

                used_satellites.add(
                    meosar_id
                )

            break

    # ======================================================
    # Fill remaining operational antennas
    # ======================================================

    for antenna_name, antenna_data in sorted(
        antennas.items()
    ):

        if not antenna_data["operational"]:
            continue

        if antenna_name in assignments:
            continue

        for candidate in candidates:

            meosar_id = candidate["meosar_id"]
            band = candidate["band"]

            # Don't track the same satellite twice.

            if meosar_id in used_satellites:
                continue

            # Antenna must support the satellite band.

            if band not in antenna_data["bands"]:
                continue

            assignments[
                antenna_name
            ] = candidate

            used_satellites.add(
                meosar_id
            )

            break

    # ======================================================
    # Debug assignment result
    # ======================================================

    print()
    print("CURRENT SCHEDULER ASSIGNMENTS")
    print("=============================")

    for antenna_name, assignment in (
        assignments.items()
    ):

        print(
            "  ",
            antenna_name,
            "→",
            assignment["meosar_id"],
            "| Score:",
            round(
                assignment["score"],
                2,
            ),
        )

    if strategy and (strategy.get("geometry") or strategy.get("locations")):
        from core.group_strategy import choose_group
        assignments=choose_group(candidates,antennas,current_assignments,assignments,strategy)
    return assignments


# ==========================================================
# Runs scheduler across entire mission window
# ==========================================================

def run_scheduler(
    satellites,
    antennas,
    goddard,
    mission,
    strategy=None,
):
    """
    Runs the MEOSAR scheduler minute-by-minute
    across the mission window.
    """

    strategy = dict(strategy or {})
    strategy["geometry"] = True
    if strategy.get("enabled") is False:
        strategy["locations"] = []

    schedule = []

    current_assignments = {}

    # ======================================================
    # Calculate pre-event priorities once
    # ======================================================

    satellite_priorities = (
        calculate_satellite_priorities(
            satellites,
            goddard,
            mission.location,
            mission,
        )
    )

    print()
    print("PRE-EVENT SATELLITE PRIORITIES")
    print("==============================")

    for meosar_id, priority in (
        satellite_priorities.items()
    ):

        print(
            meosar_id,
            "| Qualified:",
            priority["qualified"],
            "| Earliest:",
            priority["earliest_visibility"],
            "| Lead Time:",
            round(
                priority["lead_time_minutes"],
                1,
            ),
            "minutes",
        )

    print()

    # ======================================================
    # Mission time window
    # ======================================================

    current_datetime = mission.get_start_time()
    end_datetime = mission.get_end_time()

    # ======================================================
    # Ensure Python datetime objects
    # ======================================================

    if not isinstance(
        current_datetime,
        datetime,
    ):
        current_datetime = (
            current_datetime.utc_datetime()
        )

    if not isinstance(
        end_datetime,
        datetime,
    ):
        end_datetime = (
            end_datetime.utc_datetime()
        )

    # ======================================================
    # Force UTC
    # ======================================================

    if current_datetime.tzinfo is None:

        current_datetime = (
            current_datetime.replace(
                tzinfo=timezone.utc
            )
        )

    if end_datetime.tzinfo is None:

        end_datetime = (
            end_datetime.replace(
                tzinfo=timezone.utc
            )
        )

    # ======================================================
    # Run minute-by-minute
    # ======================================================

    while current_datetime < end_datetime:

        print(
            "Calculating:",
            current_datetime,
        )

        skyfield_time = ts.from_datetime(
            current_datetime
        )

        # ==================================================
        # Check existing assignments
        # ==================================================

        for antenna, assignment in list(
            current_assignments.items()
        ):

            if should_switch_satellite(
                assignment,
                goddard,
                mission.location,
                skyfield_time,
            ):

                print(
                    "Switch needed:",
                    antenna,
                    "lost MEOSAR",
                    assignment["meosar_id"],
                )

                del current_assignments[
                    antenna
                ]

        # ==================================================
        # Create new assignments
        # ==================================================

        new_assignments = create_assignment(
            satellites,
            antennas,
            goddard,
            mission.location,
            skyfield_time,
            current_assignments,
            satellite_priorities,
            strategy=strategy,
        )

        # ==================================================
        # Replace current assignments
        # ==================================================

        current_assignments = new_assignments

        # ==================================================
        # Save scheduler state
        # ==================================================

        schedule.append(
            {
                "time": current_datetime,
                "end": min(current_datetime + timedelta(minutes=1), end_datetime),
                "assignments":
                    current_assignments.copy(),
            }
        )

        # ==================================================
        # Advance one minute
        # ==================================================

        current_datetime += timedelta(
            minutes=1
        )

    return schedule


# ==========================================================
# Compress minute-by-minute schedule
# ==========================================================

def compress_schedule(schedule):
    """
    Converts the minute-by-minute schedule into
    start/end tracking blocks.

    Removes any tracking pass shorter than
    MINIMUM_PASS_DURATION_MINUTES.

    Preserves:
        - NORAD ID
        - MEOSAR ID
        - band
        - score
    """

    compressed = {}

    # ======================================================
    # Build complete compressed schedule
    # ======================================================

    for entry in schedule:

        time = entry["time"]
        assignments = entry["assignments"]
        interval_end = entry.get("end", time + timedelta(minutes=1))
        if interval_end <= time:
            raise ValueError("Schedule sample end must be after its start.")

        for antenna, satellite in assignments.items():

            meosar_id = satellite["meosar_id"]

            # ----------------------------------------------
            # Get NORAD ID
            # ----------------------------------------------

            norad_id = satellite.get(
                "norad_id",
                ""
            )

            # ----------------------------------------------
            # Create antenna list
            # ----------------------------------------------

            if antenna not in compressed:

                compressed[antenna] = []

            # ----------------------------------------------
            # First assignment for this antenna
            # ----------------------------------------------

            if not compressed[antenna]:

                compressed[antenna].append(
                    {
                        "start": time,
                        "end": interval_end,

                        "norad_id": norad_id,

                        "meosar_id": meosar_id,

                        "band": satellite["band"],

                        "score": satellite["score"],
                    }
                )

                continue

            # ----------------------------------------------
            # Get current tracking block
            # ----------------------------------------------

            current = compressed[antenna][-1]

            # ----------------------------------------------
            # Same satellite
            # ----------------------------------------------

            if (str(current["meosar_id"]) == str(meosar_id)
                    and str(current.get("norad_id", "")) == str(norad_id)
                    and current["end"] == time):
                current["end"] = interval_end

            # ----------------------------------------------
            # Satellite changed
            # ----------------------------------------------

            else:

                compressed[antenna].append(
                    {
                        "start": time,
                        "end": interval_end,

                        "norad_id": norad_id,

                        "meosar_id": meosar_id,

                        "band": satellite["band"],

                        "score": satellite["score"],
                    }
                )

    # ======================================================
    # Remove passes shorter than minimum duration
    # ======================================================

    minimum_duration = timedelta(
        minutes=MINIMUM_PASS_DURATION_MINUTES
    )

    filtered_compressed = {}

    for antenna, tracks in compressed.items():

        valid_tracks = []

        for track in tracks:

            duration = (
                track["end"]
                -
                track["start"]
            )

            if duration >= minimum_duration:

                valid_tracks.append(
                    track
                )

            else:

                print()
                print(
                    "REMOVING SHORT PASS"
                )

                print(
                    "Antenna:",
                    antenna
                )

                print(
                    "MEOSAR:",
                    track["meosar_id"]
                )

                print(
                    "Start:",
                    track["start"]
                )

                print(
                    "End:",
                    track["end"]
                )

                print(
                    "Duration:",
                    duration
                )

                print(
                    "Minimum:",
                    minimum_duration
                )

        filtered_compressed[antenna] = valid_tracks

    # ======================================================
    # Return complete filtered schedule
    # ======================================================

    return filtered_compressed


# ==========================================================
# Determines whether current satellite should be switched
# ==========================================================

def should_switch_satellite(
    current_satellite,
    goddard,
    mission_site,
    time,
):
    """
    Determines whether the currently tracked satellite
    should be replaced.

    Switch reasons:

    1. Satellite is no longer visible from Goddard.
    2. Satellite is no longer visible from mission site.
    """

    if current_satellite is None:
        return True

    satellite = current_satellite["satellite"]

    # ======================================================
    # Check Goddard visibility
    # ======================================================

    goddard_view = calculate_visibility(
        satellite,
        goddard,
        time,
        observer_name="Goddard",
    )

    # ======================================================
    # Check mission-site visibility
    # ======================================================

    mission_view = calculate_visibility(
        satellite,
        mission_site,
        time,
        observer_name="Mission Site",
    )

    # ======================================================
    # Lost Goddard visibility
    # ======================================================

    if not goddard_view["visible"]:
        return True

    # ======================================================
    # Lost mission-site visibility
    # ======================================================

    if not mission_view["visible"]:
        return True

    return False