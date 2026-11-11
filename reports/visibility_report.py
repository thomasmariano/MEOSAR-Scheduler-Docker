# reports/visibility_report.py
"""Minute-sampled mutual visibility with explicit interval-end metadata."""
from datetime import timedelta, timezone
from core.visibility import calculate_visibility


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def generate_mutual_visibility_report(satellites, goddard, mission, start_time, end_time, ts):
    """Return sampled visibility for both endpoints, including empty windows.

    `end` retains its legacy meaning: the last visible sample timestamp.
    `end_exclusive` is that sample's interval end, clipped to the mission limit.
    This preserves existing graph/editor consumers while making interval bounds
    explicit. One-minute sampling does not resolve changes within each minute.
    """
    start_time, end_time = _utc(start_time), _utc(end_time)
    if end_time <= start_time:
        raise ValueError("Visibility report end must be after its start.")
    prepared = {}
    owners = {}
    report = {}
    for satellite in satellites:
        norad = str(satellite.model.satnum).strip()
        meosar = str(getattr(satellite, "meosar_id", None) or norad)
        if meosar in owners and owners[meosar] != norad:
            raise ValueError(f"MEOSAR ID {meosar} is assigned to multiple NORAD IDs.")
        owners[meosar] = norad
        prepared[norad] = satellite
        report[norad] = {"norad_id": norad, "meosar_id": meosar,
                         "sample_seconds": 60, "end_semantics": "last_visible_sample",
                         "windows": []}
    current = start_time
    while current < end_time:
        sample_end = min(current + timedelta(minutes=1), end_time)
        skyfield_time = ts.from_datetime(current)
        for norad, satellite in prepared.items():
            ground = calculate_visibility(satellite, goddard, skyfield_time, observer_name="Goddard")
            site = calculate_visibility(satellite, mission.location, skyfield_time, observer_name="Mission")
            if not (ground.get("visible", False) and site.get("visible", False)):
                continue
            windows = report[norad]["windows"]
            if windows and windows[-1]["end_exclusive"] == current:
                windows[-1]["end"] = current
                windows[-1]["end_exclusive"] = sample_end
            else:
                windows.append({"start": current, "end": current, "end_exclusive": sample_end})
        current = sample_end
    return sorted(report.values(), key=lambda row: (
        not row["meosar_id"].isdigit(),
        int(row["meosar_id"]) if row["meosar_id"].isdigit() else row["meosar_id"],
        row["norad_id"],
    ))
