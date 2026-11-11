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
# NORAD LOOKUP
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

def generate_all_satellite_coverage_graph(
    satellite_visibility,
    enabled_satellites,
    mission_name,
    mission_start,
    mission_end,
    event_time,
    event_type=None,
    ground_station_location=None,
    landing_site_location=None,
    *, output_directory=None,
):

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
    # SELECTED SATELLITES ONLY
    # ======================================================

    selected_ids = {
        str(value)
        for value in enabled_satellites
    }

    satellites = []

    for satellite in satellite_visibility:

        satellite_id = _satellite_id(
            satellite
        )

        if satellite_id not in selected_ids:

            continue

        satellites.append(
            satellite
        )

    # ======================================================
    # SORT
    # ======================================================

    satellites.sort(
        key=_satellite_sort_key
    )

    satellite_count = len(
        satellites
    )

    # ======================================================
    # EMPTY
    # ======================================================

    if satellite_count == 0:

        figure, axis = plt.subplots(
            figsize=(16, 7)
        )

        axis.text(
            0.5,
            0.5,
            "No selected MEOSAR satellites",
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
            event_time=event_time,
            maximum_visible=0,
            ground_station_location=ground_station_location,
            landing_site_location=landing_site_location
        )

        axis.set_axis_off()

        output_file = (
            output_dir
            /
            "all_satellite_coverage.png"
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
        satellite_count * 0.32
    )

    figure, (axis, count_axis) = plt.subplots(
        2, 1, sharex=True,
        figsize=(16, figure_height + 1.4),
        gridspec_kw={"height_ratios": [max(3, satellite_count * .32), 1.4], "hspace": .10}
    )

    # ======================================================
    # SATELLITE ROWS
    # ======================================================

    satellite_labels = []

    for row_number, satellite in enumerate(
        satellites
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

            axis.text(
                mission_start,
                row_number,
                "No Coverage",
                fontsize=7,
                alpha=0.6,
                va="center"
            )

            continue

        for window in windows:

            start_time = window["start"]
            end_time = window.get("end_exclusive", window["end"])

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

    for satellite in satellites:

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

    maximum_visible = max(
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
        alpha=0.75,
        label="Total Visible Satellites"
    )

    count_axis.set_ylim(
        0,
        max(
            maximum_visible,
            1
        )
    )

    count_axis.set_ylabel(
        "Total Visible Satellites"
    )

    count_axis.grid(False)

    # ======================================================
    # LEFT Y AXIS
    # ======================================================

    axis.set_yticks(
        range(
            satellite_count
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
        event_time,
        linestyle="--",
        linewidth=2
    )

    axis.annotate(
        "EVENT\n"
        +
        event_time.strftime(
            "%H:%M UTC"
        ),
        xy=(
            event_time,
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
        fontsize=8,
        fontweight="bold",
        ha="left",
        va="top"
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
        event_time=event_time,
        maximum_visible=maximum_visible,
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
        "all_satellite_coverage.png"
    )

    polish_timeline(figure,axis,mission_start,mission_end,satellite_count,count_axis)

    figure.savefig(
        output_file,
        dpi=300,
        bbox_inches="tight"
    )

    plt.close(figure)

    return output_file