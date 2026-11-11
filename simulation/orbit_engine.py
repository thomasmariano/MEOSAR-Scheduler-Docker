#simulation/orbit_engine.py
"""SGP4 orbit propagation for MEOSAR simulation.

Schedule timestamps are UTC. SGP4 positions are TEME; Earth-fixed
positions use an approximate GMST rotation suitable for visualization
and preliminary geometric visibility calculations.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sgp4.api import Satrec, jday
from skyfield.api import EarthSatellite, load, wgs84
from core.visibility import calculate_visibility


DEFAULT_TLE_DIRECTORY = (
    Path.home()
    / "Library"
    / "Application Support"
    / "MEOSAR Scheduler"
    / "TLE Library"
)

EARTH_RADIUS_KM = 6378.137
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Simulation timestamps must be timezone-aware UTC.")
    return value.astimezone(timezone.utc)


def _gmst_radians(when: datetime) -> float:
    """Approximate Greenwich Mean Sidereal Time."""
    when = _utc(when)
    year, month, day = when.year, when.month, when.day

    hour = (
        when.hour
        + when.minute / 60.0
        + (when.second + when.microsecond / 1_000_000) / 3600.0
    )

    if month <= 2:
        year -= 1
        month += 12

    a = math.floor(year / 100)
    b = 2 - a + math.floor(a / 4)

    jd = (
        math.floor(365.25 * (year + 4716))
        + math.floor(30.6001 * (month + 1))
        + day + b - 1524.5 + hour / 24.0
    )

    centuries = (jd - 2451545.0) / 36525.0

    degrees = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * centuries**2
        - centuries**3 / 38710000.0
    )

    return math.radians(degrees % 360.0)


def _teme_to_ecef(
    x: float, y: float, z: float, when: datetime
) -> tuple[float, float, float]:
    """Rotate TEME XYZ into approximate Earth-fixed XYZ, in km."""
    theta = _gmst_radians(when)
    c, s = math.cos(theta), math.sin(theta)
    return c * x + s * y, -s * x + c * y, z


def _ecef_to_geodetic(
    x: float, y: float, z: float
) -> tuple[float, float, float]:
    """Return geodetic latitude/longitude in degrees and altitude in km."""
    longitude = math.atan2(y, x)
    p = math.hypot(x, y)

    latitude = math.atan2(z, p * (1.0 - WGS84_E2))

    for _ in range(8):
        sin_lat = math.sin(latitude)
        n = EARTH_RADIUS_KM / math.sqrt(
            1.0 - WGS84_E2 * sin_lat**2
        )
        latitude = math.atan2(
            z + WGS84_E2 * n * sin_lat,
            p,
        )

    sin_lat = math.sin(latitude)
    cos_lat = math.cos(latitude)
    n = EARTH_RADIUS_KM / math.sqrt(
        1.0 - WGS84_E2 * sin_lat**2
    )

    if abs(cos_lat) > 1e-10:
        altitude = p / cos_lat - n
    else:
        altitude = abs(z) - n * (1.0 - WGS84_E2)

    return math.degrees(latitude), math.degrees(longitude), altitude


def _location_ecef(
    latitude_deg: float,
    longitude_deg: float,
    elevation_m: float = 0.0,
) -> tuple[float, float, float]:
    """Convert a WGS84 station location to Earth-fixed XYZ, in km."""
    lat = math.radians(latitude_deg)
    lon = math.radians(longitude_deg)
    altitude = elevation_m / 1000.0

    n = EARTH_RADIUS_KM / math.sqrt(
        1.0 - WGS84_E2 * math.sin(lat) ** 2
    )

    return (
        (n + altitude) * math.cos(lat) * math.cos(lon),
        (n + altitude) * math.cos(lat) * math.sin(lon),
        (n * (1.0 - WGS84_E2) + altitude) * math.sin(lat),
    )


def _elevation_angle(
    satellite_xyz: tuple[float, float, float],
    latitude_deg: float,
    longitude_deg: float,
    elevation_m: float = 0.0,
) -> float:
    """Calculate topocentric elevation in degrees."""
    sx, sy, sz = satellite_xyz
    gx, gy, gz = _location_ecef(
        latitude_deg, longitude_deg, elevation_m
    )

    dx, dy, dz = sx - gx, sy - gy, sz - gz
    lat = math.radians(latitude_deg)
    lon = math.radians(longitude_deg)

    east = -math.sin(lon) * dx + math.cos(lon) * dy
    north = (
        -math.sin(lat) * math.cos(lon) * dx
        - math.sin(lat) * math.sin(lon) * dy
        + math.cos(lat) * dz
    )
    up = (
        math.cos(lat) * math.cos(lon) * dx
        + math.cos(lat) * math.sin(lon) * dy
        + math.sin(lat) * dz
    )

    return math.degrees(math.atan2(up, math.hypot(east, north)))


class OrbitEngine:
    """Load TLE candidates and propagate satellite positions."""

    def __init__(self, tle_directory: str | Path | None = None):
        self.tle_directory = Path(
            tle_directory or DEFAULT_TLE_DIRECTORY
        ).expanduser()

        self.satellites: dict[str, dict[str, Any]] = {}
        self.tle_candidates: dict[str, list[dict[str, Any]]] = {}
        self.load_errors: list[str] = []
        self._timescale = load.timescale(builtin=True)
        self._visibility_satellites = {}
        self._visibility_observers = {}
        self._visibility_time_key = None
        self._visibility_results = {}
        self.tle_reference_time = None

    def set_tle_reference_time(self, when):
        """Choose one record per satellite around the mission event, like scheduling."""
        self.tle_reference_time = None if when is None else _utc(when)


    @staticmethod
    def _satellite_id(line: str) -> str | None:
        if len(line) < 7 or line[0] not in ("1", "2"):
            return None
        return line[2:7].strip()

    @staticmethod
    def _tle_epoch(line1: str) -> datetime:
        epoch_field = line1[18:32].strip()
        year_short = int(epoch_field[:2])
        day_of_year = float(epoch_field[2:])
        year = 2000 + year_short if year_short < 57 else 1900 + year_short

        return datetime(
            year, 1, 1, tzinfo=timezone.utc
        ) + timedelta(days=day_of_year - 1)

    def load_tle_file(self, file_path: str | Path) -> int:
        path = Path(file_path)
        lines = path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()

        loaded = 0

        for index, raw_line in enumerate(lines):
            line1 = raw_line.strip()
            if not line1.startswith("1 "):
                continue

            line2 = None
            for raw_candidate in lines[index + 1:]:
                candidate = raw_candidate.strip()

                if candidate.startswith("1 "):
                    break
                if candidate.startswith("2 "):
                    line2 = candidate
                    break

            if not line2:
                continue

            norad1 = self._satellite_id(line1)
            norad2 = self._satellite_id(line2)

            if not norad1 or norad1 != norad2:
                self.load_errors.append(
                    f"{path.name}: mismatched TLE pair near {line1!r}"
                )
                continue

            try:
                satellite = Satrec.twoline2rv(line1, line2)
                epoch = self._tle_epoch(line1)
            except Exception as exc:
                self.load_errors.append(
                    f"{path.name}: satellite {norad1}: {exc}"
                )
                continue

            record = {
                "satellite": satellite,
                "norad_id": norad1,
                "source_file": str(path),
                "epoch_utc": epoch,
                "line1": line1,
                "line2": line2,
            }

            self.tle_candidates.setdefault(norad1, []).append(record)
            loaded += 1

        return loaded

    def load_library(self) -> dict[str, Any]:
        self.satellites.clear()
        self.tle_candidates.clear()
        self.load_errors.clear()

        if not self.tle_directory.exists():
            return {
                "loaded": 0,
                "files_found": 0,
                "directory": str(self.tle_directory),
                "errors": ["TLE library directory does not exist."],
            }

        files = sorted(
            path for path in self.tle_directory.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".tle", ".txt", ".3le"}
        )

        for path in files:
            try:
                self.load_tle_file(path)
            except OSError as exc:
                self.load_errors.append(f"{path}: {exc}")

        # Keep a default record for compatibility with existing callers.
        # propagate() chooses the best candidate for each requested time.
        for norad_id, candidates in self.tle_candidates.items():
            self.satellites[norad_id] = max(
                candidates, key=lambda r: r["epoch_utc"]
            )

        return {
            "loaded": len(self.satellites),
            "tle_records": sum(
                len(items) for items in self.tle_candidates.values()
            ),
            "files_found": len(files),
            "directory": str(self.tle_directory),
            "errors": self.load_errors.copy(),
        }

    def _select_record(
        self, norad_id: str, when: datetime
    ) -> dict[str, Any]:
        candidates = self.tle_candidates.get(norad_id)

        if not candidates:
            if norad_id in self.satellites:
                return self.satellites[norad_id]
            raise KeyError(f"No TLE loaded for satellite {norad_id}.")

        reference = self.tle_reference_time or when
        return min(
            candidates,
            key=lambda record: abs(
                (reference - record["epoch_utc"]).total_seconds()
            ),
        )

    def propagate(
        self,
        norad_id: str | int,
        simulation_time: datetime,
    ) -> dict[str, Any]:
        """Propagate one satellite; include TEME and Earth-fixed positions."""
        key = str(norad_id).strip()
        when = _utc(simulation_time)
        record = self._select_record(key, when)
        return self._propagate_record(key, when, record)

    def _propagate_record(
        self,
        key: str,
        when: datetime,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """Propagate with an explicitly selected TLE record."""
        satellite = record["satellite"]

        jd, fraction = jday(
            when.year,
            when.month,
            when.day,
            when.hour,
            when.minute,
            when.second + when.microsecond / 1_000_000,
        )

        error_code, position, velocity = satellite.sgp4(jd, fraction)

        if error_code != 0:
            from sgp4.api import SGP4_ERRORS
            description = SGP4_ERRORS.get(
                error_code, f"SGP4 error {error_code}"
            )
            raise RuntimeError(
                f"Propagation failed for {key} at {when.isoformat()}: "
                f"{description}"
            )

        age_hours = (
            when - record["epoch_utc"]
        ).total_seconds() / 3600.0

        ecef = _teme_to_ecef(
            position[0], position[1], position[2], when
        )
        latitude, longitude, altitude = _ecef_to_geodetic(*ecef)

        return {
            "tle_line1": record["line1"],
            "tle_line2": record["line2"],
            "norad_id": key,
            "simulation_time_utc": when.isoformat(),
            "tle_epoch_utc": record["epoch_utc"].isoformat(),
            "tle_age_hours": round(age_hours, 2),
            "tle_age_warning": (
                "TLE epoch is in the future"
                if age_hours < 0
                else "TLE is 30+ days old"
                if age_hours >= 720
                else ""
            ),
            "source_file": record["source_file"],
            "frame": "TEME",
            "position_km": {
                "x": position[0], "y": position[1], "z": position[2]
            },
            "velocity_km_s": {
                "x": velocity[0], "y": velocity[1], "z": velocity[2]
            },
            "ecef_km": {
                "x": ecef[0], "y": ecef[1], "z": ecef[2]
            },
            "subpoint": {
                "latitude": latitude,
                "longitude": longitude,
                "altitude_km": altitude,
            },
        }

    def visibility_from_location(
        self,
        propagated: dict[str, Any],
        location: dict[str, Any],
        minimum_elevation_deg: float = 3.0,
    ) -> dict[str, Any]:
        """Use the scheduler function with this propagation's exact TLE and UTC time."""
        when = _utc(datetime.fromisoformat(propagated["simulation_time_utc"].replace("Z", "+00:00")))
        pair = (propagated["tle_line1"], propagated["tle_line2"])
        if pair not in self._visibility_satellites:
            self._visibility_satellites[pair] = EarthSatellite(
                pair[0], pair[1], str(propagated["norad_id"]), self._timescale
            )
        coordinates = (
            float(location["latitude"]), float(location["longitude"]),
            float(location.get("elevation", 0.0)),
        )
        if coordinates not in self._visibility_observers:
            self._visibility_observers[coordinates] = wgs84.latlon(
                coordinates[0], coordinates[1], elevation_m=coordinates[2]
            )
        if self._visibility_time_key != when:
            self._visibility_time_key = when
            self._visibility_results.clear()
            self._visibility_time = self._timescale.from_datetime(when)
        visibility_key = (pair, coordinates, float(minimum_elevation_deg), location.get("name", "Station"))
        if visibility_key in self._visibility_results:
            return dict(self._visibility_results[visibility_key])
        view = calculate_visibility(
            self._visibility_satellites[pair],
            self._visibility_observers[coordinates],
            self._visibility_time,
            minimum_elevation=minimum_elevation_deg,
            observer_name=location.get("name", "Station"),
        )
        result = {
            **view,
            "location": view["observer"],
            "minimum_elevation_deg": minimum_elevation_deg,
            "visibility_model": "skyfield_shared_geometric",
        }
        self._visibility_results[visibility_key] = result
        return dict(result)

    def propagate_schedule(
        self,
        assignments: list[dict[str, Any]],
        simulation_time: datetime,
    ) -> list[dict[str, Any]]:
        results = []
        seen = set()

        for assignment in assignments:
            norad_id = str(assignment["satellite_id"]).strip()
            if norad_id in seen:
                continue
            seen.add(norad_id)

            try:
                results.append(self.propagate(norad_id, simulation_time))
            except (KeyError, RuntimeError, ValueError) as exc:
                results.append({"norad_id": norad_id, "error": str(exc)})

        return results

    def propagate_library(
        self,
        simulation_time: datetime,
    ) -> list[dict[str, Any]]:
        """Propagate every unique satellite loaded from the TLE library."""
        results = []

        for norad_id in sorted(self.satellites):
            try:
                results.append(
                    self.propagate(norad_id, simulation_time)
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                results.append({
                    "norad_id": norad_id,
                    "error": str(exc),
                })

        return results

    def propagate_orbit_track(
        self,
        norad_id: str | int,
        simulation_time: datetime,
        samples: int = 48,
    ) -> dict[str, Any]:
        """
        Sample approximately one orbital revolution around the requested
        time. Returns Earth-fixed orbit positions and ground-track points.
        """
        key = str(norad_id).strip()
        when = _utc(simulation_time)
        record = self._select_record(key, when)
        mean_motion = float(record["satellite"].no_kozai)

        if not math.isfinite(mean_motion) or mean_motion <= 0:
            raise ValueError(
                f"Invalid mean motion for satellite {key}."
            )

        # SGP4 mean motion is in radians per minute.
        period_seconds = (2.0 * math.pi / mean_motion) * 60.0

        samples = max(12, min(int(samples), 360))
        start_time = when - timedelta(seconds=period_seconds / 2.0)

        orbit_points = []
        ground_track = []
        sample_times_ms = []

        for index in range(samples + 1):
            sample_time = start_time + timedelta(
                seconds=period_seconds * index / samples
            )

            sample_times_ms.append(sample_time.timestamp() * 1000.0)
            # Keep one TLE across the track so record changes cannot create jumps.
            result = self._propagate_record(key, sample_time, record)
            ecef = result["ecef_km"]
            subpoint = result["subpoint"]

            orbit_points.append([
                ecef["x"],
                ecef["y"],
                ecef["z"],
            ])

            ground_track.append([
                subpoint["latitude"],
                subpoint["longitude"],
            ])

        return {
            "satellite_id": key,
            "period_seconds": period_seconds,
            "sample_times_ms": sample_times_ms,
            "orbit_points": orbit_points,
            "ground_track": ground_track,
        }
        

    def visibility_footprint(
        self,
        propagated: dict[str, Any],
        minimum_elevation_deg: float = 3.0,
        samples: int = 72,
    ) -> dict[str, Any]:
        """
        Calculate a satellite's geometric visibility footprint on a
        spherical Earth.

        Args:
            propagated: Result returned by propagate().
            minimum_elevation_deg: Minimum elevation at the ground.
                Zero degrees represents the geometric horizon.
            samples: Number of points around the footprint boundary.

        Returns:
            A dictionary containing ordered latitude/longitude boundary
            points, the footprint center, and geometric metadata.

        Note:
            This is a spherical-Earth visualization model. It does not
            model beacon link budgets or operational SAR detection.
        """
        if not 0.0 <= minimum_elevation_deg < 90.0:
            raise ValueError(
                "Minimum elevation must be between 0 and 90 degrees."
            )

        samples = max(24, min(int(samples), 360))

        ecef = propagated["ecef_km"]
        sx = float(ecef["x"])
        sy = float(ecef["y"])
        sz = float(ecef["z"])

        satellite_radius = math.sqrt(sx * sx + sy * sy + sz * sz)

        if not math.isfinite(satellite_radius):
            raise ValueError("Satellite position is not finite.")

        if satellite_radius <= EARTH_RADIUS_KM:
            raise ValueError(
                "Satellite position must be outside the spherical Earth."
            )

        # Unit vector from Earth's center toward the satellite.
        radial = (
            sx / satellite_radius,
            sy / satellite_radius,
            sz / satellite_radius,
        )

        elevation = math.radians(minimum_elevation_deg)

        # Central angle between the subpoint and the footprint boundary.
        # Derived from the satellite-ground-Earth-center triangle.
        ratio = (
            EARTH_RADIUS_KM * math.cos(elevation)
            / satellite_radius
        )
        ratio = max(-1.0, min(1.0, ratio))

        central_angle = (
            math.pi / 2.0
            - elevation
            - math.asin(ratio)
        )

        # Construct two perpendicular tangent directions at the
        # satellite's geocentric subpoint.
        reference = (
            (0.0, 1.0, 0.0)
            if abs(radial[2]) > 0.95
            else (0.0, 0.0, 1.0)
        )

        east = (
            reference[1] * radial[2]
            - reference[2] * radial[1],
            reference[2] * radial[0]
            - reference[0] * radial[2],
            reference[0] * radial[1]
            - reference[1] * radial[0],
        )

        east_norm = math.sqrt(sum(value * value for value in east))
        east = tuple(value / east_norm for value in east)

        north = (
            radial[1] * east[2] - radial[2] * east[1],
            radial[2] * east[0] - radial[0] * east[2],
            radial[0] * east[1] - radial[1] * east[0],
        )

        cos_angle = math.cos(central_angle)
        sin_angle = math.sin(central_angle)

        boundary = []

        for index in range(samples):
            azimuth = 2.0 * math.pi * index / samples
            north_weight = sin_angle * math.cos(azimuth)
            east_weight = sin_angle * math.sin(azimuth)

            # Direction from Earth's center to a boundary point.
            x = (
                cos_angle * radial[0]
                + north_weight * north[0]
                + east_weight * east[0]
            )
            y = (
                cos_angle * radial[1]
                + north_weight * north[1]
                + east_weight * east[1]
            )
            z = (
                cos_angle * radial[2]
                + north_weight * north[2]
                + east_weight * east[2]
            )

            latitude = math.degrees(
                math.atan2(z, math.hypot(x, y))
            )
            longitude = math.degrees(math.atan2(y, x))

            boundary.append({
                "latitude": latitude,
                "longitude": longitude,
            })

        # The satellite's geocentric subpoint is the footprint center.
        center_latitude = math.degrees(
            math.atan2(sz, math.hypot(sx, sy))
        )
        center_longitude = math.degrees(math.atan2(sy, sx))

        return {
            "norad_id": str(propagated["norad_id"]),
            "center": {
                "latitude": center_latitude,
                "longitude": center_longitude,
            },
            "minimum_elevation_deg": minimum_elevation_deg,
            "central_angle_deg": math.degrees(central_angle),
            "boundary": boundary,
            "samples": samples,
            "model": "spherical_earth_geometric_visibility",
        }



class CoverageEventSearch:
    """Incrementally search for sampled crossings of the three-satellite threshold.

    Every assignment boundary is sampled. Geometric changes use a 10-second
    search grid and are refined to at most one second. Short excursions wholly
    between grid samples may be missed. Unknown visibility cannot create an event.
    """

    SAMPLE_MS = 10_000
    PRECISION_MS = 1_000

    def __init__(self, engine, assignments, locations, start_ms, end_ms,
                 origin_ms, direction=1, kind="any", minimum_elevation_deg=3.0):
        from collections import OrderedDict
        self.engine = engine
        self.assignments = [dict(a) for a in assignments]
        self.locations = [dict(p) for p in locations]
        self.start_ms = int(start_ms)
        self.end_ms = int(end_ms)
        self.origin_ms = max(self.start_ms, min(self.end_ms, int(origin_ms)))
        self.direction = 1 if direction >= 0 else -1
        self.kind = kind if kind in {"loss", "recovery"} else "any"
        self.minimum_elevation_deg = minimum_elevation_deg
        self.boundaries = sorted({int(a[k]) for a in self.assignments for k in ("startMs", "endMs")})
        self.cache = OrderedDict()
        self.unknown_samples = 0

    def _sample(self, timestamp):
        timestamp = int(timestamp)
        if timestamp in self.cache:
            self.cache.move_to_end(timestamp)
            return self.cache[timestamp]
        when = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)
        active_ids = {
            str(a["satellite_id"]).strip() for a in self.assignments
            if a["startMs"] <= timestamp < a["endMs"]
        }
        counts = {p["id"]: {"count": 0, "unknown": 0} for p in self.locations}
        for satellite_id in sorted(active_ids):
            try:
                propagated = self.engine.propagate(satellite_id, when)
            except (KeyError, RuntimeError, ValueError, OverflowError):
                for value in counts.values():
                    value["unknown"] += 1
                continue
            for location in self.locations:
                value = counts[location["id"]]
                try:
                    visibility = self.engine.visibility_from_location(
                        propagated, location,
                        minimum_elevation_deg=self.minimum_elevation_deg,
                    )
                    if visibility["visible"]:
                        value["count"] += 1
                except (KeyError, TypeError, ValueError, OverflowError):
                    value["unknown"] += 1
        for value in counts.values():
            value["state"] = True if value["count"] >= 3 else (
                False if value["count"] + value["unknown"] < 3 else None
            )
        if any(p["unknown"] for p in counts.values()):
            self.unknown_samples += 1
        self.cache[timestamp] = counts
        if len(self.cache) > 512:
            self.cache.popitem(last=False)
        yield {"status": "progress", "timeMs": timestamp}
        return counts

    def _refine(self, left, right, location_id, left_sample, right_sample):
        before_state = left_sample[location_id]["state"]
        # Preserve exact assignment transitions instead of rounding them.
        if right in self.boundaries:
            just_before = yield from self._sample(right - 1)
            if just_before[location_id]["state"] is not None and (
                just_before[location_id]["state"] != right_sample[location_id]["state"]
            ):
                return right, just_before[location_id], right_sample[location_id], 0.001
        while right - left > self.PRECISION_MS:
            middle = (left + right) // 2
            middle_sample = yield from self._sample(middle)
            state = middle_sample[location_id]["state"]
            if state is None:
                return None
            if state == before_state:
                left, left_sample = middle, middle_sample
            else:
                right, right_sample = middle, middle_sample
        return right, left_sample[location_id], right_sample[location_id], (right-left)/1000.0

    def run(self):
        from bisect import bisect_left, bisect_right
        cursor = self.origin_ms if self.direction > 0 else self.origin_ms - 1
        sample = yield from self._sample(cursor)
        limit = self.end_ms if self.direction > 0 else self.start_ms - 1
        while (cursor < limit if self.direction > 0 else cursor > limit):
            if self.direction > 0:
                candidate = min(limit, (cursor // self.SAMPLE_MS + 1) * self.SAMPLE_MS)
                index = bisect_right(self.boundaries, cursor)
                if index < len(self.boundaries):
                    candidate = min(candidate, self.boundaries[index])
            else:
                candidate = max(limit, ((cursor-1) // self.SAMPLE_MS) * self.SAMPLE_MS)
                index = bisect_left(self.boundaries, cursor) - 1
                if index >= 0:
                    candidate = max(candidate, self.boundaries[index])
            next_sample = yield from self._sample(candidate)
            if self.direction > 0:
                left, right, left_sample, right_sample = cursor, candidate, sample, next_sample
            else:
                left, right, left_sample, right_sample = candidate, cursor, next_sample, sample
            events = []
            for location in self.locations:
                identifier = location["id"]
                before = left_sample[identifier]["state"]
                after = right_sample[identifier]["state"]
                if before is None or after is None or before == after:
                    continue
                event_kind = "recovery" if after else "loss"
                if self.kind != "any" and event_kind != self.kind:
                    continue
                refined = yield from self._refine(left, right, identifier, left_sample, right_sample)
                if refined is None:
                    continue
                time_ms, before_value, after_value, precision = refined
                if (self.direction > 0 and time_ms <= self.origin_ms) or (self.direction < 0 and time_ms >= self.origin_ms):
                    continue
                events.append({
                    "locationId": identifier, "locationName": location["name"],
                    "timeMs": time_ms, "kind": event_kind,
                    "beforeCount": before_value["count"], "afterCount": after_value["count"],
                    "beforeUnknown": before_value["unknown"], "afterUnknown": after_value["unknown"],
                    "precisionSeconds": precision,
                })
            if events:
                event_time = (min if self.direction > 0 else max)(e["timeMs"] for e in events)
                yield {"status": "found", "timeMs": event_time,
                       "events": [e for e in events if e["timeMs"] == event_time],
                       "sampleSeconds": self.SAMPLE_MS / 1000.0,
                       "unknownSamples": self.unknown_samples}
                return
            cursor, sample = candidate, next_sample
        yield {"status": "none", "sampleSeconds": self.SAMPLE_MS / 1000.0,
               "unknownSamples": self.unknown_samples}
