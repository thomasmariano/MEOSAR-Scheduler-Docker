"""Compatibility entry point for core location conversion."""
from config.config_manager import load_locations
from config.library_service import get_skyfield_locations


def get_locations():
    """Load configured locations and convert them to Skyfield positions."""
    return get_skyfield_locations()
