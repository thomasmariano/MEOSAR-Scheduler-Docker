# graphs/schedule_graph.py

from pathlib import Path
from datetime import datetime, time, timezone

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from .satellite_colors import get_satellite_color
from .plot_style import polish_timeline, natural_key
from .graph_annotations import (
    add_schedule_label,
    add_graph_information
)


# ==========================================================
# OUTPUT DIRECTORY
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIRECTORY = PROJECT_ROOT / "output"


# ==========================================================
# TIME CONVERSION
# ==========================================================

def convert_time(value, event_time=None):
    """
    Convert a schedule time into a UTC timezone-aware datetime.
    """

    # Already a datetime
    if isinstance(value, datetime):

        if value.tzinfo is not None:
            return value.astimezone(timezone.utc)

        return value.replace(tzinfo=timezone.utc)

    # Python time object
    if isinstance(value, time):

        if isinstance(event_time, datetime):
            date = event_time.date()
        else:
            date = datetime.now(timezone.utc).date()

        return datetime.combine(
            date,
            value
        ).replace(tzinfo=timezone.utc)

    # Nothing supplied
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    # ISO datetime
    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )

        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc)

        return parsed.replace(tzinfo=timezone.utc)

    except ValueError:
        pass

    # HH:MM / HH:MM:SS
    for format_string in ("%H:%M", "%H:%M:%S"):

        try:
            parsed_time = datetime.strptime(
                text,
                format_string
            ).time()

            if isinstance(event_time, datetime):
                date = event_time.date()
            else:
                date = datetime.now(timezone.utc).date()

            return datetime.combine(
                date,
                parsed_time
            ).replace(tzinfo=timezone.utc)

        except ValueError:
            continue

    return None


# ==========================================================
# NORMALIZE SCHEDULE
# ==========================================================

def normalize_schedule(schedule, event_time=None):
    """
    Convert supported schedule formats into one consistent
    dictionary format:

        {
            "Antenna 1": [
                {
                    "start": datetime,
                    "end": datetime,
                    "meosar_id": "...",
                    "norad_id": "...",
                    "band": "..."
                }
            ]
        }
    """

    normalized = {}

    # ======================================================
    # DICTIONARY SCHEDULE
    # ======================================================

    if isinstance(schedule, dict):

        for antenna, tracks in schedule.items():

            if not isinstance(tracks, list):
                continue

            antenna_name = str(antenna)

            normalized.setdefault(
                antenna_name,
                []
            )

            for track in tracks:

                if not isinstance(track, dict):
                    continue

                start = convert_time(
                    track.get("start"),
                    event_time
                )

                end = convert_time(
                    track.get("end"),
                    event_time
                )

                if start is None or end is None:
                    continue

                if end <= start:
                    continue

                normalized[antenna_name].append({
                    "start": start,
                    "end": end,
                    "meosar_id": track.get(
                        "meosar_id",
                        track.get(
                            "satellite",
                            "Unknown"
                        )
                    ),
                    "norad_id": track.get(
                        "norad_id",
                        ""
                    ),
                    "band": track.get(
                        "band",
                        ""
                    )
                })

    # ======================================================
    # FLAT LIST
    # ======================================================

    elif isinstance(schedule, list):

        for track in schedule:

            if not isinstance(track, dict):
                continue

            antenna = str(
                track.get(
                    "antenna",
                    "Unknown Antenna"
                )
            )

            start = convert_time(
                track.get("start"),
                event_time
            )

            end = convert_time(
                track.get("end"),
                event_time
            )

            if start is None or end is None:
                continue

            if end <= start:
                continue

            normalized.setdefault(
                antenna,
                []
            )

            normalized[antenna].append({
                "start": start,
                "end": end,
                "meosar_id": track.get(
                    "meosar_id",
                    track.get(
                        "satellite",
                        "Unknown"
                    )
                ),
                "norad_id": track.get(
                    "norad_id",
                    ""
                ),
                "band": track.get(
                    "band",
                    ""
                )
            })

    # ======================================================
    # SORT TRACKS
    # ======================================================

    for antenna in normalized:

        normalized[antenna].sort(
            key=lambda track: track["start"]
        )

    return normalized


# ==========================================================
# GENERATE GRAPH
# ==========================================================

def generate_schedule_graph(
    schedule,
    mission_name=None,
    event_time=None,
    event_type=None,
    mission_start=None,
    mission_end=None,
    ground_station_location=None,
    landing_site_location=None,
    *, output_directory=None,
):
    """
    Generate and save the MEOSAR tracking schedule graph.

    Returns:
        Path to the generated PNG file.
    """

    output_dir = Path(output_directory) if output_directory is not None else OUTPUT_DIRECTORY
    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # ======================================================
    # NORMALIZE EVENT TIME
    # ======================================================

    normalized_event_time = convert_time(
        event_time
    )

    # ======================================================
    # NORMALIZE SCHEDULE
    # ======================================================

    normalized_schedule = normalize_schedule(
        schedule,
        normalized_event_time
    )

    # ======================================================
    # ANTENNAS
    # ======================================================

    antennas = sorted((antenna for antenna,tracks in normalized_schedule.items() if tracks),key=natural_key)

    # ======================================================
    # EMPTY SCHEDULE
    # ======================================================

    if not antennas:

        figure, axis = plt.subplots(
            figsize=(12, 6)
        )

        axis.text(
            0.5,
            0.5,
            "No tracking assignments available",
            ha="center",
            va="center",
            transform=axis.transAxes
        )

        axis.set_title(
            f"MEOSAR Tracking Schedule Coverage of {landing_site_location}"
        )

        add_graph_information(axis,event_name=mission_name,event_type=event_type,start_time=convert_time(mission_start),
            end_time=convert_time(mission_end),event_time=normalized_event_time,
            ground_station_location=ground_station_location,landing_site_location=landing_site_location)
        polish_timeline(figure,axis,convert_time(mission_start),convert_time(mission_end),0)
        axis.set_axis_off()

        output_file = (
            output_dir /
            "tracking_schedule.png"
        )

        figure.savefig(
            output_file,
            dpi=300,
            bbox_inches="tight"
        )

        plt.close(figure)

        return output_file

    # ======================================================
    # CREATE FIGURE
    # ======================================================

    figure_height = max(
        8,
        len(antennas) * 0.8 + 4
    )

    figure, axis = plt.subplots(
        figsize=(15, figure_height)
    )

    # ======================================================
    # Y POSITIONS
    # ======================================================

    y_positions = {
        antenna: index
        for index, antenna in enumerate(antennas)
    }

    # ======================================================
    # ALL TRACKS
    # ======================================================

    all_tracks = [
        track
        for tracks in normalized_schedule.values()
        for track in tracks
    ]

    graph_start = min(
        track["start"]
        for track in all_tracks
    )

    graph_end = max(
        track["end"] for track in all_tracks
    )
    # Show the complete scheduling window, including unassigned gaps at its ends.
    graph_start=convert_time(mission_start,normalized_event_time) or graph_start
    graph_end=convert_time(mission_end,normalized_event_time) or graph_end

    axis.set_xlim(graph_start,graph_end)

    # ======================================================
    # DRAW TRACKS
    # ======================================================

    for antenna in antennas:
        tracks=normalized_schedule[antenna]
        y_position = y_positions[antenna]

        # Alternate short-pass labels above/below
        short_pass_index = 0

        for track in tracks:

            start_time = track["start"]
            end_time = track["end"]

            satellite = str(
                track.get(
                    "meosar_id",
                    "Unknown"
                )
            )

            # --------------------------------------------------
            # Duration
            # --------------------------------------------------

            duration_seconds = (
                end_time - start_time
            ).total_seconds()

            duration_days = (
                duration_seconds / 86400.0
            )

            # --------------------------------------------------
            # Tracking bar
            # --------------------------------------------------

            axis.barh(
                y_position,
                duration_days,
                left=mdates.date2num(start_time),
                height=0.5,
                color=get_satellite_color(satellite),
                zorder=3
            )

            # --------------------------------------------------
            # Satellite label
            # --------------------------------------------------

            label = satellite

            norad = track.get(
                "norad_id",
                ""
            )

            band = track.get(
                "band",
                ""
            )

            if norad:
                label += f"\nNORAD {norad}"

            if band:
                label += f" ({band})"

            # --------------------------------------------------
            # Long pass
            # --------------------------------------------------

            if duration_seconds >= max(180, (graph_end-graph_start).total_seconds()*.12):

                add_schedule_label(
                    axis,
                    start_time,
                    end_time,
                    y_position,
                    label,
                    label_position="auto",
                    fontsize=8
                )

            # --------------------------------------------------
            # Short pass
            # --------------------------------------------------

            else:

                label_position = (
                    "above"
                    if short_pass_index % 2 == 0
                    else "below"
                )

                add_schedule_label(
                    axis,
                    start_time,
                    end_time,
                    y_position,
                    label,
                    label_position=label_position,
                    fontsize=8
                )

                short_pass_index += 1

    # ==========================================================
    # Y AXIS
    # ==========================================================

    axis.set_yticks(
        range(len(antennas))
    )

    axis.set_yticklabels(
        antennas
    )

    axis.set_ylabel(
        "Antenna"
    )

    # ==========================================================
    # X AXIS
    # ==========================================================

    axis.set_xlim(
        graph_start,
        graph_end
    )

    axis.xaxis_date()

    axis.xaxis.set_major_formatter(
        mdates.DateFormatter(
            "%H:%M",
            tz=timezone.utc
        )
    )

    axis.set_xlabel(
        "UTC Time"
    )

    # ==========================================================
    # GRID
    # ==========================================================

    axis.grid(
        axis="x",
        linestyle="--",
        alpha=0.4,
        zorder=0
    )

    # ==========================================================
    # MISSION EVENT
    # ==========================================================

    if normalized_event_time is not None:

        axis.axvline(
            normalized_event_time,
            linestyle="--",
            linewidth=2,
            zorder=4
        )

        event_name = (
            str(event_type).upper()
            if event_type
            else "MISSION"
        )

        event_label = (
            f"{event_name} EVENT\n"
            f"{normalized_event_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

        axis.text(
            normalized_event_time,
            0.98,
            event_label,
            transform=axis.get_xaxis_transform(),
            ha="center",
            va="top",
            bbox=dict(boxstyle="round,pad=0.35",facecolor="white",edgecolor="#c5d0db",alpha=.94),
            fontsize=8,
            fontweight="bold"
        )

    # ==========================================================
    # TITLE
    # ==========================================================

    axis.set_title(
        f"MEOSAR Tracking Schedule Coverage of {landing_site_location}",
        fontsize=14,
        fontweight="bold",
        y=1.20,
        pad=0
    )
        
    add_graph_information(
        axis,
        event_name=mission_name,
        event_type=event_type,
        start_time=mission_start,
        end_time=mission_end,
        event_time=normalized_event_time,
        ground_station_location=ground_station_location,
        landing_site_location=landing_site_location,
        y_position=1.11
    )

    # ==========================================================
    # Y PADDING
    # ==========================================================

    axis.set_ylim(
        -0.6,
        len(antennas) - 0.4
    )

    # ==========================================================
    # SAVE GRAPH
    # ==========================================================

    figure.subplots_adjust(
        left=0.08,
        right=0.95,
        bottom=0.12,
        top=0.70
    )

    output_file = (
        output_dir /
        "tracking_schedule.png"
    )

    polish_timeline(figure,axis,graph_start,graph_end,len(antennas))

    figure.savefig(
        output_file,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(figure)

    return output_file