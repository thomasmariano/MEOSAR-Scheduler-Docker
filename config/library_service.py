"""Shared configuration operations without dependencies on Qt or GUI modules.

No cache is introduced: GUI edits remain visible to the next reader, as before.
Record schemas and enabled-satellite return types retain their existing meaning.
"""
from config.config_manager import load_locations, load_antennas, load_satellites


def get_all_locations():
    return load_locations()


def get_skyfield_locations():
    from skyfield.api import wgs84
    return {name: wgs84.latlon(data["latitude"], data["longitude"],
                              elevation_m=data["elevation"])
            for name, data in load_locations().items()}


def get_all_antennas():
    return load_antennas()


def get_operational_antennas():
    return {name: data for name, data in load_antennas().items()
            if data.get("operational", False)}


def get_all_satellites():
    return load_satellites()


def get_enabled_satellites():
    # Preserve existing callers' integer NORAD keys and configured MEOSAR values.
    return {int(norad): data["meosar_id"] for norad, data in load_satellites().items()
            if data.get("enabled", False)}


def get_selected_satellites():
    return get_enabled_satellites()


def get_satellite_band(meosar_id):
    for data in load_satellites().values():
        if str(data.get("meosar_id")) == str(meosar_id):
            return data.get("band")
    return None
