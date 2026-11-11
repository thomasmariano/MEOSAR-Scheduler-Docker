# satellites/satellites.py
"""
MEOSAR Satellite Management

Handles:

- Satellite configuration
- Enabled/selected satellites
- Satellite band identification
- CelesTrak GNSS TLE downloads
- TLE archive management
- Loading MEOSAR satellites from TLE files
"""

from datetime import datetime, timezone
from pathlib import Path

import requests

from skyfield.api import EarthSatellite, load

from config.library_service import (
    get_enabled_satellites,
)
from config.config_manager import load_satellites
from satellites.tle_manager import TLEManager

# ============================================================
# TLE LIBRARY
# ============================================================

TLE_ARCHIVE = (
    TLEManager.USER_TLE_DIRECTORY
)



# ============================================================
# CELESTRAK
# ============================================================

CELESTRAK_URL = (
    "https://celestrak.org/"
    "NORAD/elements/gp.php"
    "?GROUP=gnss"
    "&FORMAT=tle"
)

# ============================================================
# TLE SETTINGS
# ============================================================

MAX_TLE_AGE_DAYS = 7

# ============================================================
# SATELLITE DATABASE
# ============================================================

def get_satellite_database():
    """
    Return the complete satellite configuration database.

    Returns
    -------
    dict
        Satellite configuration loaded from satellites.json.
    """

    return load_satellites()


def get_selected_satellites():
    """
    Return the currently enabled MEOSAR satellites.

    Returns
    -------
    dict
        Mapping of NORAD ID to MEOSAR ID.

    Example
    -------
    {
        62339: "11301",
        41549: "11402"
    }
    """

    return get_enabled_satellites()


def get_satellite_band(meosar_id):
    """
    Determine the MEOSAR frequency band from the
    MEOSAR satellite ID.

    MEOSAR ID ranges:

        113xx -> S Band
        114xx -> L Band

    Parameters
    ----------
    meosar_id : str or int
        MEOSAR satellite identifier.

    Returns
    -------
    str
        "S", "L", or "Unknown".
    """

    meosar_id = str(
        meosar_id
    ).strip()


    if meosar_id.startswith("113"):
        return "S"


    if meosar_id.startswith("114"):
        return "L"


    return "Unknown"


# ============================================================
# TLE DOWNLOAD
# ============================================================

def download_tle_catalog():
    """
    Download the current GNSS TLE catalog from CelesTrak
    and save it to the local TLE archive.

    Returns
    -------
    pathlib.Path
        Path to the newly downloaded TLE file.

    Raises
    ------
    requests.RequestException
        If the CelesTrak request fails.
    """

    TLE_ARCHIVE.mkdir(parents=True, exist_ok=True)

    print(
        "Downloading GNSS TLE catalog..."
    )


    response = requests.get(
        CELESTRAK_URL,
        timeout=30
    )


    response.raise_for_status()


    now = datetime.now(
        timezone.utc
    )


    filename = (
        "gnss_"
        +
        now.strftime(
            "%Y-%m-%d_%H-%M-%S"
        )
        +
        ".tle"
    )


    file_path = (
        TLE_ARCHIVE / filename
    )


    file_path.write_text(
        response.text,
        encoding="utf-8"
    )


    print(
        "TLE catalog saved:"
    )


    print(
        file_path
    )


    return file_path


# ============================================================
# FIND BEST TLE FILE
# ============================================================

def find_best_tle_file(target_datetime):
    """
    Find the TLE archive closest to a target time.

    A TLE file is only considered valid if it is no older
    than MAX_TLE_AGE_DAYS.

    If the newest available TLE file is too old, None is
    returned so the caller can download a new catalog.

    Parameters
    ----------
    target_datetime : datetime
        Target UTC datetime.

    Returns
    -------
    pathlib.Path or None
        Best valid TLE archive file.
        None if no valid/current TLE exists.
    """

    if target_datetime.tzinfo is None:

        target_datetime = target_datetime.replace(
            tzinfo=timezone.utc
        )

    else:

        target_datetime = target_datetime.astimezone(
            timezone.utc
        )


    files = sorted(
        TLE_ARCHIVE.glob(
            "gnss_*.tle"
        )
    )


    if not files:

        print(
            "No TLE archive files found."
        )

        return None


    now = datetime.now(
        timezone.utc
    )


    best_file = None
    smallest_difference = None


    for file_path in files:

        try:

            timestamp = (
                file_path.stem
                .replace(
                    "gnss_",
                    ""
                )
            )


            file_time = datetime.strptime(
                timestamp,
                "%Y-%m-%d_%H-%M-%S"
            ).replace(
                tzinfo=timezone.utc
            )


            # ------------------------------------------------
            # Check TLE age
            # ------------------------------------------------

            age = (
                now - file_time
            ).total_seconds() / 86400


            if age > MAX_TLE_AGE_DAYS:

                print(
                    f"Skipping outdated TLE: "
                    f"{file_path.name} "
                    f"({age:.1f} days old)"
                )

                continue


            # ------------------------------------------------
            # Find closest TLE to target time
            # ------------------------------------------------

            difference = abs(
                target_datetime -
                file_time
            )


            if (
                smallest_difference is None
                or
                difference < smallest_difference
            ):

                smallest_difference = (
                    difference
                )

                best_file = file_path


        except ValueError:

            print(
                "Skipping invalid TLE archive filename:",
                file_path
            )


    if best_file is None:

        print(
            "No TLE archive is within the "
            f"{MAX_TLE_AGE_DAYS}-day maximum age."
        )


    return best_file


# ============================================================
# LOAD MEOSAR SATELLITES FROM TLE FILE
# ============================================================

def normalize_norad_id(value):
    text = str(value).strip()
    return str(int(text)) if text.isdigit() else text.upper()


def load_meosar_satellites_from_file(file_path, selected_norad_ids=None, target_datetime=None):
    """Load a run-specific selection without requiring a different TLE file.

    Omitting selected_norad_ids retains the enabled-library behavior. Supplying
    an empty iterable deliberately loads nothing. Duplicate NORAD records use
    the epoch closest to target_datetime, or the latest epoch if no time is given.
    """
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"TLE file not found: {path}")
    enabled = {normalize_norad_id(k): str(v) for k, v in get_selected_satellites().items()}
    if selected_norad_ids is None:
        selected = enabled
    else:
        requested = {normalize_norad_id(v) for v in selected_norad_ids}
        database = {normalize_norad_id(k): v for k, v in load_satellites().items()}
        selected = {}
        for identifier in requested:
            raw = database.get(identifier, {})
            meosar = raw.get("meosar_id") if isinstance(raw, dict) else raw
            if meosar is None or str(meosar).strip().lower() in {"", "unknown", "none"}:
                meosar = enabled.get(identifier)
            if meosar is not None:
                selected[identifier] = str(meosar).strip()
    if not selected:
        return []
    target = target_datetime
    if target is not None:
        target = target.replace(tzinfo=timezone.utc) if target.tzinfo is None else target.astimezone(timezone.utc)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    timescale = load.timescale()
    by_id = {}
    for index, raw in enumerate(lines):
        line1 = raw.strip()
        if not line1.startswith("1 "):
            continue
        next_index = index + 1
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1
        if next_index >= len(lines):
            continue
        line2 = lines[next_index].strip()
        if (len(line1) < 63 or len(line2) < 63 or not line2.startswith("2 ")
                or line1[2:7].strip() != line2[2:7].strip()):
            print(f"Skipping mismatched/incomplete TLE near line {index+1} in {path.name}")
            continue
        previous = lines[index-1].strip() if index else ""
        name = previous if previous and not previous.startswith(("1 ", "2 ", "#")) else "UNKNOWN"
        try:
            satellite = EarthSatellite(line1, line2, name, timescale)
            identifier = normalize_norad_id(satellite.model.satnum)
            if identifier not in selected:
                continue
            satellite.meosar_id = selected[identifier]
            satellite.norad_id = satellite.model.satnum
            satellite.band = get_satellite_band(satellite.meosar_id)
            epoch = satellite.epoch.utc_datetime()
            old = by_id.get(identifier)
            if old is not None:
                old_epoch = old.epoch.utc_datetime()
                replace = abs(epoch-target) < abs(old_epoch-target) if target is not None else epoch > old_epoch
                if not replace:
                    continue
            by_id[identifier] = satellite
        except (ValueError, TypeError, OverflowError) as exc:
            print(f"Skipping invalid TLE near line {index+1}: {exc}")
    return [by_id[k] for k in sorted(by_id, key=lambda k: (not k.isdigit(), int(k) if k.isdigit() else k))]


# ============================================================
# LOAD BEST TLE FOR TARGET TIME
# ============================================================

def load_meosar_satellites(
    target_datetime
):
    """
    Find the TLE archive closest to the requested time
    and load the configured MEOSAR satellites from it.

    Parameters
    ----------
    target_datetime : datetime
        Target UTC time.

    Returns
    -------
    list
        Loaded MEOSAR Skyfield satellites.

    Raises
    ------
    FileNotFoundError
        If no TLE archive exists.
    """

    tle_file = find_best_tle_file(
        target_datetime
    )


    if tle_file is None:

        raise FileNotFoundError(
            "No GNSS TLE files were found in the TLE archive."
        )


    print(
        "Using TLE archive:"
    )

    print(
        tle_file
    )


    return load_meosar_satellites_from_file(
        tle_file
    )