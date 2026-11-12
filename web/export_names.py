"""Desktop-compatible readable schedule names, shared by downloads and file copies."""
from datetime import datetime, timezone
import re


def clean(value):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value).strip()).rstrip('. ')[:60]


def utc(value):
    when = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)


def export_basename(result, mission, revision='original'):
    tracks = [track for rows in result.get('schedule', {}).values() for track in rows]
    try:
        start = min(utc(t['start']) for t in tracks) if tracks else utc(result['tracking_start'])
        end = max(utc(t['end']) for t in tracks) if tracks else utc(result['tracking_end'])
    except (KeyError, ValueError, TypeError):
        return 'schedule'
    name = clean(mission.get('mission_name', mission.get('name', 'Mission'))) or 'Mission'
    location = clean(mission.get('mission_location', ''))
    suffix = ' revision-'+revision[:8] if revision != 'original' else ''
    return f"{start:%Y%m%d %H%M} - {end:%Y%m%d %H%M} {name} {location}{suffix} coverage".replace('  ', ' ')
