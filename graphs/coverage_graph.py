from pathlib import Path

import matplotlib


import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from config.config_manager import load_satellites

from .satellite_colors import get_satellite_color
from .plot_style import polish_timeline
from .graph_annotations import (
    add_aos_los_labels,
    add_graph_information
)


# ==========================================================
# OUTPUT DIRECTORY
# ==========================================================

PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT / "output"
)


# ==========================================================
# SATELLITE CONFIGURATION
# ==========================================================

def _build_norad_lookup():
    """
    Build:

        MEOSAR ID -> NORAD ID

    from satellites.json.
    """

    configuration = load_satellites()

    lookup = {}

    for norad_id, satellite in configuration.items():

        meosar_id = satellite.get(
            "meosar_id"
        )

        if meosar_id is None:
            continue

        lookup[
            str(meosar_id)
        ] = str(norad_id)

    return lookup


# ==========================================================
# SATELLITE ID
# ==========================================================

def _satellite_id(satellite):

    return str(
        satellite.get(
            "meosar_id",
            satellite.get(
                "satellite",
                "Unknown"
            )
        )
    )


# ==========================================================
# NORAD ID
# ==========================================================

def _norad_id(
    satellite,
    norad_lookup
):
    """
    Resolve NORAD ID from:

    1. visibility data
    2. satellite configuration
    """

    direct_norad = satellite.get(
        "norad_id",
        satellite.get(
            "norad",
            ""
        )
    )

    if direct_norad:

        return str(
            direct_norad
        )

    return norad_lookup.get(
        _satellite_id(satellite),
        ""
    )


# ==========================================================
# SORT
# ==========================================================

def _satellite_sort_key(satellite):

    try:

        return (0, int(_satellite_id(satellite)))

    except ValueError:

        return (1, _satellite_id(satellite))


# ==========================================================
# GENERATE GRAPH
# ==========================================================

def generate_coverage_graph(
    mutual_visibility,
    mission_name,
    mission_start,
    mission_end,
    landing_time,
    selected_satellites=None,
    event_type=None,
    ground_station_location=None,
    landing_site_location=None,
    *, output_directory=None,
):
    """
    Generate the MEOSAR Mutual Visibility Timeline.

    Only selected satellites are included when
    selected_satellites is supplied.
    """

    output_dir = Path(output_directory) if output_directory is not None else OUTPUT_DIRECTORY
    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # ======================================================
    # NORAD LOOKUP
    # ======================================================

    norad_lookup = _build_norad_lookup()

    # ======================================================
    # SELECT SATELLITES
    # ======================================================

    if selected_satellites is not None:

        selected_ids = {
            str(value)
            for value in selected_satellites
        }

        filtered_visibility = [
            satellite
            for satellite in mutual_visibility
            if _satellite_id(satellite)
            in selected_ids
        ]

    else:

        filtered_visibility = list(
            mutual_visibility
        )

    # ======================================================
    # SORT
    # ======================================================

    sorted_satellites = sorted(
        filtered_visibility,
        key=_satellite_sort_key
    )

    number_of_satellites = len(
        sorted_satellites
    )

    # ======================================================
    # EMPTY DATA
    # ======================================================

    if number_of_satellites == 0:

        figure, axis = plt.subplots(
            figsize=(16, 7)
        )

        axis.text(
            0.5,
            0.5,
            "No satellite visibility data available",
            ha="center",
            va="center",
            transform=axis.transAxes
        )

        axis.set_title(
            f"MEOSAR Mutual Visibility Timeline Coverage of {landing_site_location}",
            fontsize=14,
            fontweight="bold",
            y=1.08,
            pad=0
        )

        add_graph_information(
            axis,
            event_name=mission_name,
            event_type=event_type,
            start_time=mission_start,
            end_time=mission_end,
            event_time=landing_time,
            maximum_visible=0,
            ground_station_location=ground_station_location,
            landing_site_location=landing_site_location
        )

        axis.set_axis_off()

        output_file = (
            output_dir
            /
            "satellite_coverage_timeline.png"
        )

        polish_timeline(figure,axis,mission_start,mission_end,0)
        figure.savefig(
            output_file,
            dpi=300,
            bbox_inches="tight"
        )

        plt.close(figure)

        return output_file

    # ======================================================
    # FIGURE
    # ======================================================

    figure_height = max(
        10,
        number_of_satellites * 0.32
    )

    figure, (axis, count_axis) = plt.subplots(
        2, 1, sharex=True,
        figsize=(16, figure_height + 1.4),
        gridspec_kw={"height_ratios": [max(3, number_of_satellites * .32), 1.4], "hspace": .10}
    )

    # ======================================================
    # SATELLITE ROWS
    # ======================================================

    satellite_labels = []

    for row_number, satellite in enumerate(
        sorted_satellites
    ):

        meosar_id = _satellite_id(
            satellite
        )

        norad_id = _norad_id(
            satellite,
            norad_lookup
        )

        if norad_id:

            satellite_labels.append(
                f"{meosar_id} | NORAD {norad_id}"
            )

        else:

            satellite_labels.append(
                f"{meosar_id} | NORAD UNKNOWN"
            )

        windows = satellite.get(
            "windows",
            []
        )

        if not windows:
            axis.annotate('No coverage',xy=(mission_start,row_number),xytext=(6,0),textcoords='offset points',fontsize=7,color='#64748b',va='center')
        for window in windows:

            start_time = window["start"]
            end_time = window.get("end_exclusive", window["end"])

            # --------------------------------------------------
            # Clip to graph
            # --------------------------------------------------

            if start_time < mission_start:

                start_time = mission_start

            if end_time > mission_end:

                end_time = mission_end

            if start_time >= end_time:

                continue

            duration_days = (
                end_time - start_time
            ).total_seconds() / 86400

            axis.barh(
                row_number,
                duration_days,
                left=mdates.date2num(
                    start_time
                ),
                height=0.55,
                align="center",
                color=get_satellite_color(
                    meosar_id
                ),
                zorder=3
            )

            add_aos_los_labels(
                axis,
                start_time,
                end_time,
                row_number,
                graph_start=mission_start,
                graph_end=mission_end,
                fontsize=7
            )

    # ======================================================
    # VISIBILITY EVENTS
    # ======================================================

    visibility_events = []

    for satellite in sorted_satellites:

        for window in satellite.get(
            "windows",
            []
        ):

            start_time = window["start"]
            end_time = window.get("end_exclusive", window["end"])

            if start_time < mission_start:

                start_time = mission_start

            if end_time > mission_end:

                end_time = mission_end

            if start_time >= end_time:

                continue

            visibility_events.append(
                (
                    start_time,
                    1
                )
            )

            visibility_events.append(
                (
                    end_time,
                    -1
                )
            )

    visibility_events.sort(
        key=lambda event: (
            event[0],
            event[1]
        )
    )

    # ======================================================
    # COUNT TIMELINE
    # ======================================================

    count_times = [
        mission_start
    ]

    count_values = [
        0
    ]

    current_count = 0
    deltas = {}
    for timestamp,change in visibility_events:
        deltas[timestamp]=deltas.get(timestamp,0)+change
    for timestamp,change in sorted(deltas.items()):
        current_count += change
        count_times.append(timestamp)
        count_values.append(current_count)

    if count_times[-1] != mission_end:

        count_times.append(
            mission_end
        )

        count_values.append(
            current_count
        )

    maximum_mutual_visibility = max(
        count_values
    )

    # ======================================================
    # RIGHT AXIS
    # ======================================================

    # Counts occupy a separate strip so they do not obscure satellite rows.

    count_axis.step(
        count_times,
        count_values,
        where="post",
        linewidth=2.5,
        alpha=0.5,
        label="Mutually Visible Satellites"
    )

    y_axis_max = max(
        maximum_mutual_visibility,
        1
    )

    count_axis.set_ylim(
        0,
        y_axis_max
    )

    count_axis.set_yticks(
        range(
            0,
            y_axis_max + 1
        )
    )

    count_axis.set_ylabel(
        "Total Mutually Visible Satellites"
    )

    count_axis.grid(False)

    # ======================================================
    # LEFT AXIS
    # ======================================================

    axis.set_yticks(
        range(
            number_of_satellites
        )
    )

    axis.set_yticklabels(
        satellite_labels,
        fontsize=10,
        fontweight="bold"
    )

    axis.set_ylabel(
        "MEOSAR Satellite"
    )

    # ======================================================
    # X AXIS
    # ======================================================

    axis.set_xlim(
        mission_start,
        mission_end
    )

    axis.xaxis.set_major_locator(
        mdates.HourLocator(
            interval=1
        )
    )

    axis.xaxis.set_major_formatter(
        mdates.DateFormatter(
            "%H:%M",
            tz=mission_start.tzinfo
        )
    )

    axis.set_xlabel(
        "UTC Time"
    )

    plt.setp(
        axis.get_xticklabels(),
        rotation=45,
        ha="right"
    )

    # ======================================================
    # EVENT
    # ======================================================

    axis.axvline(
        landing_time,
        linewidth=2,
        linestyle="--"
    )

    axis.annotate(
        "EVENT\n"
        +
        landing_time.strftime(
            "%H:%M UTC"
        ),
        xy=(
            landing_time,
            1
        ),
        xycoords=(
            "data",
            "axes fraction"
        ),
        xytext=(
            5,
            -5
        ),
        textcoords="offset points",
        ha="left",
        va="top",
        fontsize=8,
        fontweight="bold"
    )

    # ======================================================
    # GRID
    # ======================================================

    axis.grid(
        axis="x",
        linestyle="--",
        alpha=0.4
    )

    # ======================================================
    # TITLE
    # ======================================================

    axis.set_title(
        f"MEOSAR Mutual Visibility Timeline Coverage of {landing_site_location}",
        fontsize=14,
        fontweight="bold",
        y=1.08,
        pad=0
    )

    # ======================================================
    # GRAPH INFORMATION
    # ======================================================

    add_graph_information(
        axis,
        event_name=mission_name,
        event_type=event_type,
        start_time=mission_start,
        end_time=mission_end,
        event_time=landing_time,
        maximum_visible=maximum_mutual_visibility,
        ground_station_location=ground_station_location,
        landing_site_location=landing_site_location
    )

    # ======================================================
    # LEGEND
    # ======================================================

    count_axis.legend(
        loc="upper right"
    )

    # ======================================================
    # SAVE
    # ======================================================

    output_file = (
        output_dir
        /
        "satellite_coverage_timeline.png"
    )

    polish_timeline(figure,axis,mission_start,mission_end,number_of_satellites,count_axis)

    figure.savefig(
        output_file,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(figure)

    return output_file