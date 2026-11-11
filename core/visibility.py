"""Shared geometric visibility for scheduler and simulator (no refraction)."""

def calculate_visibility(satellite, observer, time, minimum_elevation=3,
                         observer_name=None):
    """Return unrounded topocentric angles and an inclusive elevation mask."""
    for name, value in (("Satellite", satellite), ("Observer", observer), ("Time", time)):
        if isinstance(value, str):
            raise TypeError(f"{name} is a string: {value}")
    altitude, azimuth, distance = (satellite.at(time) - observer.at(time)).altaz()
    elevation = float(altitude.degrees)
    return {
        "observer": observer_name,
        "elevation_deg": elevation,
        "azimuth_deg": float(azimuth.degrees),
        "range_km": float(distance.km),
        "visible": bool(elevation >= minimum_elevation),
    }
