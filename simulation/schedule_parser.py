# simulation/schedule_parser.py
"""Parse MEOSAR scheduler assignment files.

Supported rows:
satellite_id,field_2,field_3,start_time,end_time

Example:
38833,2,2,10/01/2026 15:10:00,10/01/2026 16:25:00
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


DATE_FORMATS = (
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


@dataclass(frozen=True)
class Assignment:
    satellite_id: str
    field_2: str
    field_3: str
    start: datetime
    end: datetime

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    @property
    def duration_minutes(self) -> float:
        return self.duration_seconds / 60.0

    def to_dict(self) -> dict:
        return {
            "satellite_id": self.satellite_id,
            "field_2": self.field_2,
            "field_3": self.field_3,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class ParsedSchedule:
    source: str
    assignments: list[Assignment]
    warnings: list[str]

    @property
    def start(self) -> datetime:
        return min(a.start for a in self.assignments)

    @property
    def end(self) -> datetime:
        return max(a.end for a in self.assignments)

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    @property
    def satellite_ids(self) -> list[str]:
        return sorted(
            {a.satellite_id for a in self.assignments},
            key=lambda value: (not value.isdigit(),
                               int(value) if value.isdigit() else value),
        )

    @property
    def resource_ids(self) -> list[str]:
        return sorted({a.field_3 for a in self.assignments})

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_seconds": self.duration_seconds,
            "assignment_count": len(self.assignments),
            "satellite_ids": self.satellite_ids,
            "resource_ids": self.resource_ids,
            "assignments": [a.to_dict() for a in self.assignments],
            "warnings": self.warnings,
        }


def _parse_datetime(value: str) -> datetime:
    value = value.strip()

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    raise ValueError(
        f"Unsupported date/time {value!r}. "
        "Expected MM/DD/YYYY HH:MM:SS."
    )


def parse_schedule_text(
    text: str,
    source: str = "<pasted schedule>",
) -> ParsedSchedule:
    """Parse a schedule from CSV-like text with optional blank lines."""

    assignments: list[Assignment] = []
    warnings: list[str] = []
    errors: list[str] = []

    reader = csv.reader(io.StringIO(text.lstrip("\ufeff")))

    for line_number, row in enumerate(reader, start=1):
        if not row or all(not cell.strip() for cell in row):
            continue

        # Permit a header row in future exports.
        first = row[0].strip().lower()
        if first in {"satellite_id", "satellite", "norad_id"}:
            continue

        if len(row) != 5:
            errors.append(
                f"Line {line_number}: expected 5 columns, got {len(row)}."
            )
            continue

        satellite_id, field_2, field_3, start_text, end_text = (
            cell.strip() for cell in row
        )

        if not satellite_id or not field_2 or not field_3:
            errors.append(f"Line {line_number}: an ID/parameter is empty.")
            continue

        try:
            start = _parse_datetime(start_text)
            end = _parse_datetime(end_text)
        except ValueError as exc:
            errors.append(f"Line {line_number}: {exc}")
            continue

        if end <= start:
            errors.append(
                f"Line {line_number}: end time must be after start time."
            )
            continue

        assignments.append(
            Assignment(
                satellite_id=satellite_id,
                field_2=field_2,
                field_3=field_3,
                start=start,
                end=end,
            )
        )

    if errors:
        raise ValueError(
            "Schedule contains invalid rows:\n\n" + "\n".join(errors)
        )

    if not assignments:
        raise ValueError("No valid schedule assignments were found.")

    assignments.sort(key=lambda a: (a.start, a.end, a.satellite_id))

    # Check for temporal overlaps within each field_3 group.
    # This flags potential conflicts, not necessarily actual conflicts:
    # field_3 semantics and resource constraints must be confirmed.
    by_resource: dict[str, list[Assignment]] = {}
    for assignment in assignments:
        by_resource.setdefault(assignment.field_3, []).append(assignment)

    for resource, rows in by_resource.items():
        rows.sort(key=lambda a: a.start)

        for previous, current in zip(rows, rows[1:]):
            if current.start < previous.end:
                warnings.append(
                    f"Potential overlap in field_3={resource}: "
                    f"{previous.satellite_id} and {current.satellite_id}."
                )

    # Gaps between assignments in a group are not automatically errors.
    return ParsedSchedule(
        source=source,
        assignments=assignments,
        warnings=warnings,
    )


def load_schedule_file(path: str | Path) -> ParsedSchedule:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    return parse_schedule_text(text, source=path.name)


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours:02}:{minutes:02}:{secs:02}"
    return f"{minutes:02}:{secs:02}"
