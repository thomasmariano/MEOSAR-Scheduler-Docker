# scheduler/scheduler_controller.py
"""
MEOSAR Scheduler Controller

Connects the PyQt GUI to the scheduling engine.

The controller:

1. Reads GUI configuration
2. Loads locations
3. Creates the Mission
4. Loads the TLE file selected by the GUI
5. Loads enabled MEOSAR satellites
6. Loads operational antennas
7. Runs the scheduler
8. Generates visibility reports
9. Generates coverage graphs
10. Generates the tracking schedule graph
"""

from datetime import timezone
from copy import deepcopy
import math

from skyfield.api import load, wgs84

from core.mission import Mission
from core.schedule_diagnostics import analyze_schedule, format_schedule_diagnostics
from core.scheduler import MINIMUM_PASS_DURATION_MINUTES

from config.config_manager import load_locations

from satellites.satellites import (
    load_meosar_satellites_from_file,
    get_selected_satellites,
    normalize_norad_id,
)


from core.scheduler import (
    run_scheduler,
    compress_schedule,
)

from reports.visibility_report import (
    generate_mutual_visibility_report,
)

from graphs.coverage_graph import (
    generate_coverage_graph,
)

from graphs.coverage_graph_all import (
    generate_all_satellite_coverage_graph,
)

from graphs.schedule_graph import (
    generate_schedule_graph,
)


class SchedulerController:

    """
    Main controller used by the MEOSAR GUI.
    """

    def __init__(self):

        self.ts = load.timescale()


    # ========================================================
    # UTC Conversion
    # ========================================================

    @staticmethod
    def ensure_utc(
        datetime_value
    ):
        """
        Ensure a datetime is timezone-aware UTC.
        """

        if datetime_value.tzinfo is None:

            return datetime_value.replace(
                tzinfo=timezone.utc
            )

        return datetime_value.astimezone(
            timezone.utc
        )


    # ========================================================
    # Skyfield Location
    # ========================================================

    def get_skyfield_location(
        self,
        location_name
    ):
        """
        Convert a saved JSON location into
        a Skyfield geographic position.
        """

        locations = load_locations()

        if location_name not in locations:

            raise ValueError(

                f"Location "
                f"'{location_name}' "
                f"not found."

            )

        data = locations[
            location_name
        ]

        return wgs84.latlon(

            data["latitude"],

            data["longitude"],

            elevation_m=data["elevation"]

        )


    # ========================================================
    # Validate Configuration
    # ========================================================

    def validate_config(
        self,
        config
    ):
        """
        Validate the configuration received from the GUI.
        """

        required_fields = [

            "mission_name",

            "mission_location",

            "ground_station",

            "hours_before",

            "hours_after",

            "event_time",

            "satellites",

            "antennas",

            "tle_file",

        ]

        for field in required_fields:

            if field not in config:

                raise ValueError(

                    f"Missing scheduler configuration: "
                    f"{field}"

                )


        if not config["mission_name"].strip():

            raise ValueError(
                "Mission name cannot be empty."
            )


        if (
            not config["mission_location"]
            or
            config["mission_location"]
            == "-- Select Mission Site --"
        ):

            raise ValueError(
                "Please select a mission site."
            )


        if not config["ground_station"]:

            raise ValueError(
                "Please select a ground station."
            )


        if not config["satellites"]:

            raise ValueError(
                "No MEOSAR satellites are enabled."
            )


        if not config["antennas"]:

            raise ValueError(
                "No antennas are configured."
            )


        if not isinstance(config["antennas"], dict):
            raise ValueError("Antenna configuration must be a mapping.")
        durations = [float(config[key]) for key in ("hours_before", "hours_after")]
        if any(not math.isfinite(value) or value < 0 for value in durations) or sum(durations) <= 0:
            raise ValueError("Mission coverage durations must be finite, nonnegative, and total more than zero.")

        if not config["tle_file"]:

            raise ValueError(
                "No TLE file was selected."
            )


    # ========================================================
    # Main Scheduler
    # ========================================================

    def run(
        self,
        config,
        *, output_directory=None,
    ):
        """
        Run the complete MEOSAR scheduling workflow.

        Returns
        -------
        dict
            Scheduler output used by the GUI.
        """

        print()
        print(
            "============================"
        )
        print(
            "RUNNING MEOSAR SCHEDULER"
        )
        print(
            "============================"
        )


        # ====================================================
        # Validate GUI configuration
        # ====================================================

        self.validate_config(
            config
        )


        # ====================================================
        # Event time
        # ====================================================

        event_time = self.ensure_utc(
            config["event_time"]
        )

        config = dict(config)
        config["hours_before"] = float(config["hours_before"])
        config["hours_after"] = float(config["hours_after"])
        config["event_time"] = event_time

        print(
            "Event UTC:",
            event_time
        )

        # ====================================================
        # Locations
        # ====================================================

        ground_station_name = config["ground_station"]
        landing_site_name = config["mission_location"]

        print(
            "Ground Station:",
            ground_station_name
        )

        print(
            "Landing Site:",
            landing_site_name
        )

        print(
            "Loading ground station..."
        )

        ground_station = self.get_skyfield_location(
            ground_station_name
        )

        print(
            "Loading mission site..."
        )

        mission_site = self.get_skyfield_location(
            landing_site_name
        )


        # ====================================================
        # Mission
        # ====================================================

        mission = Mission(

            name=config["mission_name"],

            location=mission_site,

            event_time=event_time,

            hours_before=config["hours_before"],

            hours_after=config["hours_after"]

        )


        print(
            "Mission created:"
        )

        print(
            mission
        )


        # ====================================================
        # Mission time range
        # ====================================================

        start_time = (
            mission.get_start_time()
        )

        end_time = (
            mission.get_end_time()
        )


        # ====================================================
        # TLE
        # ====================================================

        tle_file = config[
            "tle_file"
        ]

        print(
            "Using TLE:",
            tle_file
        )


        tle_info = (
            config.get(
                "tle_info"
            )
        )

        if tle_info:

            print(
                "TLE source:",
                tle_info.get(
                    "source",
                    "Unknown"
                )
            )

            print(
                "TLE mode:",
                tle_info.get(
                    "mode",
                    tle_info.get(
                        "selection",
                        "Unknown"
                    )
                )
            )

            if tle_info.get(
                "age_hours"
            ) is not None:

                print(
                    "TLE age:",
                    f"{tle_info['age_hours']:.1f} hours"
                )


        # ====================================================
        # Satellites
        # ====================================================

        requested_ids = {normalize_norad_id(value) for value in config["satellites"]}
        library_ids = {normalize_norad_id(value) for value in get_selected_satellites()}
        all_loaded_satellites = load_meosar_satellites_from_file(
            tle_file, selected_norad_ids=library_ids | requested_ids,
            target_datetime=event_time,
        )
        meosar_owners = {}
        for satellite in all_loaded_satellites:
            meosar_id = str(satellite.meosar_id)
            norad_id = normalize_norad_id(satellite.model.satnum)
            if meosar_id in meosar_owners and meosar_owners[meosar_id] != norad_id:
                raise ValueError(f"MEOSAR ID {meosar_id} is configured for multiple NORAD IDs.")
            meosar_owners[meosar_id] = norad_id
        satellites = [sat for sat in all_loaded_satellites
                      if normalize_norad_id(sat.model.satnum) in requested_ids]
        loaded_ids = {normalize_norad_id(sat.model.satnum) for sat in satellites}
        selection_audit = {
            "requested_norad_ids": sorted(requested_ids),
            "used_norad_ids": sorted(loaded_ids),
            "missing_norad_ids": sorted(requested_ids-loaded_ids),
        }
        print("Run satellite selection:", selection_audit)

        print(
            "Satellites loaded:",
            len(satellites)
        )


        if not satellites:

            raise RuntimeError(

                "None of the selected satellites have usable configured TLE records. "
                f"Requested NORAD IDs: {', '.join(sorted(requested_ids))}"

            )


        # ====================================================
        # Antennas
        # ====================================================

        antennas = {
            name: deepcopy(data) for name, data in config["antennas"].items()
            if isinstance(data, dict) and data.get("operational", False)
        }


        print(
            "Operational antennas:"
        )


        for name, data in antennas.items():

            print(
                f" - {name}: "
                f"Bands={data.get('bands', [])}"
            )


        if not antennas:

            raise RuntimeError(
                "No operational antennas available."
            )


        # ====================================================
        # Run scheduler
        # ====================================================

        print(
            "Running scheduler..."
        )


        strategy=deepcopy(config.get("scheduling_strategy",{}))
        for site in strategy.get("locations",[]):
            lat=float(site["latitude"]);lon=float(site["longitude"])
            height=float(site.get("elevation",0));weight=float(site.get("weight",1))
            if not all(math.isfinite(v) for v in (lat,lon,height,weight)) or not -90<=lat<=90 or not -180<=lon<=180 or not .1<=weight<=10:
                raise ValueError("Invalid alternate location coordinates or weight.")
            site["observer"]=wgs84.latlon(lat,lon,elevation_m=height)

        schedule = run_scheduler(

            satellites,

            antennas,

            ground_station,

            mission,
            strategy=strategy

        )


        # ====================================================
        # Compress schedule
        # ====================================================

        compressed_schedule = (
            compress_schedule(
                schedule
            )
        )


        schedule_diagnostics = analyze_schedule(
            schedule, compressed_schedule, start_time, end_time,
            minimum_minutes=MINIMUM_PASS_DURATION_MINUTES,
        )
        print(format_schedule_diagnostics(schedule_diagnostics))

        # ====================================================
        # Schedule graph
        # ====================================================

        print(
            "Generating tracking schedule graph..."
        )

        schedule_graph = generate_schedule_graph(
            schedule=compressed_schedule,
            mission_name=mission.name,
            event_time=event_time,
            event_type=config.get("event_type"),
            mission_start=start_time,
            mission_end=end_time,
            ground_station_location=ground_station_name,
            landing_site_location=landing_site_name,
            output_directory=output_directory,
        )


        # ====================================================
        # Visibility report
        # ====================================================

        print(
            "Generating mutual visibility report..."
        )


        all_visibility = (
            generate_mutual_visibility_report(

                all_loaded_satellites,

                ground_station,

                mission,

                start_time,

                end_time,

                self.ts

            )
        )


        visibility = [row for row in all_visibility
                      if normalize_norad_id(row["norad_id"]) in loaded_ids]

        # ====================================================
        # Standard coverage graph
        # ====================================================

        print(
            "Generating coverage graph..."
        )


        graph_file = generate_coverage_graph(
            visibility,
            mission.name,
            start_time,
            end_time,
            mission.event_time,
            event_type=config.get("event_type"),
            ground_station_location=ground_station_name,
            landing_site_location=landing_site_name,
            output_directory=output_directory,
        )


        # ====================================================
        # Determine enabled MEOSAR IDs
        # ====================================================

        enabled_meosar_ids = []


        selected_norad_ids = {

            normalize_norad_id(norad)

            for norad in config["satellites"]

        }


        for satellite in satellites:

            satellite_norad = str(
                satellite.model.satnum
            )


            if (
                satellite_norad
                in selected_norad_ids
            ):

                enabled_meosar_ids.append(
                    str(
                        satellite.meosar_id
                    )
                )


        enabled_meosar_ids = list(
            dict.fromkeys(
                enabled_meosar_ids
            )
        )


        print(
            "Enabled MEOSAR IDs:"
        )

        print(
            enabled_meosar_ids
        )


        # ====================================================
        # Complete visibility list
        # ====================================================

        all_satellite_visibility = []


        visibility_by_id = {

            str(item["meosar_id"]):
                item

            for item in all_visibility

        }


        for satellite in all_loaded_satellites:

            meosar_id = str(
                satellite.meosar_id
            )


            if (
                meosar_id
                in visibility_by_id
            ):

                all_satellite_visibility.append(

                    visibility_by_id[
                        meosar_id
                    ]

                )

            else:

                all_satellite_visibility.append({

                    "meosar_id":
                        meosar_id,

                    "windows":
                        []

                })


        # ====================================================
        # All satellite coverage graph
        # ====================================================

        print(
            "Generating all-satellite coverage graph..."
        )

        all_graph_file = generate_all_satellite_coverage_graph(
            all_satellite_visibility,
            enabled_meosar_ids,
            mission.name,
            start_time,
            end_time,
            mission.event_time,
            event_type=config.get("event_type"),
            ground_station_location=ground_station_name,
            landing_site_location=landing_site_name,
            output_directory=output_directory,
        )


        # ====================================================
        # Return GUI results
        # ====================================================

        return {

            # ================================================
            # EDITABLE TRACKING SCHEDULE
            # ================================================

            "schedule":
                compressed_schedule,

            # ================================================
            # MUTUAL VISIBILITY INFORMATION
            # ================================================

            "visibility":
                visibility,

            # ================================================
            # GENERATED GRAPHS
            # ================================================

            "graph_file":
                graph_file,

            "all_graph_file":
                all_graph_file,

            "schedule_graph":
                schedule_graph,

            # ================================================
            # MISSION
            # ================================================

            "mission":
                mission,

            # ================================================
            # SATELLITES
            # ================================================

            "satellites":
                satellites,

            # ================================================
            # EXPLICIT TRACKING WINDOW
            # ================================================

            "tracking_start":
                start_time,

            "tracking_end":
                end_time,

            # ================================================
            # EVENT TIME
            # ================================================

            "event_time":
                event_time,

            # ================================================
            # TLE INFORMATION
            # ================================================

            "tle_file":
                tle_file,

            "tle_info":
                tle_info,
            "selection_audit": selection_audit,
            "schedule_diagnostics": schedule_diagnostics,
            "scheduling_strategy": deepcopy(config.get("scheduling_strategy",{})),

        }