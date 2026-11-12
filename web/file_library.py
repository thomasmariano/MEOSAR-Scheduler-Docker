"""One-way, readable export copies; canonical application records stay under /data."""
from pathlib import Path
from threading import Event, Thread
import json
import logging
import os
import re
import shutil
import tempfile
from .export_names import export_basename

logger = logging.getLogger(__name__)
GRAPHS = ('tracking_schedule.png', 'satellite_coverage_timeline.png', 'all_satellite_coverage.png')
SCHEDULES = ('schedule.txt', 'schedule.metadata.json', 'result.json')


def read_json(path):
    return json.loads(path.read_text())


def label(value):
    value = re.sub(r'[^A-Za-z0-9 _.-]', '_', str(value)).strip(' .')[:60]
    return value or 'Mission'


def copy_file(source, destination):
    if not source.is_file() or source.is_symlink():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size == source.stat().st_size and destination.stat().st_mtime_ns == source.stat().st_mtime_ns:
        return
    # Atomic copies prevent readers seeing an incomplete report/video.
    fd, temporary = tempfile.mkstemp(prefix='.export-', dir=destination.parent)
    os.close(fd)
    try:
        shutil.copy2(source, temporary)
        os.chmod(temporary, 0o640)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


class FileLibrary:
    INTERVAL = 15

    def __init__(self, root):
        self.root = Path(root)
        exports = os.environ.get('MEOSAR_EXPORT_DIRECTORY')
        tles = os.environ.get('MEOSAR_TLE_EXPORT_DIRECTORY')
        self.exports = Path(exports) if exports else None
        self.tles = Path(tles) if tles else None
        for folder in (self.exports, self.tles):
            if folder is not None and not folder.is_absolute():
                raise ValueError('File-library locations must be absolute.')
        self.stop = Event()
        self.thread = None
        if self.exports or self.tles:
            self.thread = Thread(target=self.run, daemon=True, name='meosar-file-library')
            self.thread.start()

    def publish(self, source, key, revision='Original', saved=False):
        if self.exports is None:
            return
        prefix = 'Saved missions' if saved else 'Schedules'
        mission_path = source/'mission.json' if saved or revision == 'Original' else source.parent.parent/'mission.json'
        mission = read_json(mission_path) if mission_path.exists() else {}
        result = read_json(source/'result.json') if (source/'result.json').exists() else {}
        basename = export_basename(result, mission, result.get('edit_revision', 'original'))
        for filename in SCHEDULES:
            candidate = source/filename
            if filename != 'result.json' and not saved and revision == 'Original':
                candidate = source/'exports'/filename
            friendly = basename+('.txt' if filename == 'schedule.txt' else '.metadata.json' if filename == 'schedule.metadata.json' else '.result.json')
            if basename == 'schedule' and filename == 'result.json':friendly = filename
            destination = self.exports/prefix/key/revision/friendly
            copy_file(candidate, destination)
            old = self.exports/prefix/key/revision/filename
            if old != destination and old.is_file() and candidate.is_file() and old.read_bytes() == candidate.read_bytes():
                old.unlink()
        for filename in GRAPHS:
            candidate = source/filename if saved or revision != 'Original' else source/'graphs'/filename
            copy_file(candidate, self.exports/'Graphs'/key/revision/filename)

    def sync(self):
        errors = 0
        if self.exports:
            for name in ('Schedules', 'Graphs', 'Videos', 'Saved missions'):
                (self.exports/name).mkdir(parents=True, exist_ok=True)
            for job in (self.root/'jobs').iterdir():
                try:
                    if not job.is_dir() or job.is_symlink() or read_json(job/'status.json').get('state') != 'completed':
                        continue
                    mission = read_json(job/'mission.json')
                    key = label(mission.get('mission_name', 'Mission'))+'__'+job.name
                    self.publish(job, key)
                    history = read_json(job/'editor.json').get('history', []) if (job/'editor.json').exists() else []
                    retained = read_json(job/'retained-revisions.json') if (job/'retained-revisions.json').exists() else []
                    for revision in set(history+retained)-{'original'}:
                        if not re.fullmatch(r'[a-f0-9-]{36}', revision):
                            continue
                        self.publish(job/'edits'/revision, key, 'Revision '+revision)
                    for state in job.glob('videos/*/status.json'):
                        info = read_json(state)
                        filename = info.get('filename')
                        if info.get('state') == 'completed' and filename in ('video.mp4', 'video.webm'):
                            copy_file(state.parent/filename, self.exports/'Videos'/key/(state.parent.name+Path(filename).suffix))
                except (OSError, ValueError, TypeError, KeyError):
                    errors += 1
            for state in (self.root/'saved-missions').glob('*/saved.json'):
                try:
                    info = read_json(state)
                    self.publish(state.parent, label(info['name'])+'__'+state.parent.name, saved=True)
                except (OSError, ValueError, TypeError, KeyError):
                    errors += 1
        if self.tles:
            self.tles.mkdir(parents=True, exist_ok=True)
            for metadata in (self.root/'tles').glob('*.json'):
                try:
                    info = read_json(metadata)
                    key = label(info.get('name', 'TLE'))+'__'+metadata.stem
                    copy_file(metadata.with_suffix('.tle'), self.tles/(key+'.tle'))
                    copy_file(metadata, self.tles/(key+'.json'))
                except (OSError, ValueError, TypeError, KeyError):
                    errors += 1
        if errors:
            logger.warning('File library skipped %d unavailable/incomplete records; retrying on next scan.', errors)

    def run(self):
        while not self.stop.is_set():
            try:
                self.sync()
            except (OSError, ValueError):
                logger.exception('File library could not refresh; canonical app data remains unchanged.')
            self.stop.wait(self.INTERVAL)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=10)
