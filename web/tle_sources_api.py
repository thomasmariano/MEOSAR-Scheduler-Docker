"""Browser adapters for desktop TLE sources and a configured read-only mount.

No browser-supplied URLs or absolute server paths are accepted. Credentials
are used only in the request's source session; they are never written to disk.
"""
from pathlib import Path
from threading import BoundedSemaphore
import hashlib
import os
import time

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from satellites.tle_sources.celestrak import CelesTrakSource
from satellites.tle_sources.space_track import SpaceTrackSource
from .scheduling_api import read_json, service, store_tle, _error, LIBRARIES

router = APIRouter(prefix='/api/tle-sources')
remote_slot = BoundedSemaphore(1)
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_SCAN_ENTRIES = 5000
EXTENSIONS = {'.tle', '.txt', '.3le'}


def import_root():
    value = os.environ.get('MEOSAR_TLE_IMPORT_DIR')
    if not value:
        _error('Server folder is not configured. Set MEOSAR_TLE_IMPORT_DIR.', 503)
    root = Path(value)
    if not root.is_absolute():
        _error('Server import folder must be configured as an absolute path.', 503)
    if not root.is_dir():
        _error('Server import folder is unavailable. Check the Docker mount.', 503)
    return root.resolve()


def folder_entries():
    root = import_root()
    records = []
    scanned = 0
    truncated = False
    try:
        def scan_error(error):
            raise error
        for folder, dirs, files in os.walk(root, followlinks=False, onerror=scan_error):
            relative = Path(folder).relative_to(root)
            depth = len(relative.parts)
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and
                             not (Path(folder)/d).is_symlink()) if depth < 3 else []
            scanned += len(dirs) + len(files)
            for name in sorted(files):
                path = Path(folder)/name
                if path.suffix.lower() not in EXTENSIONS or path.is_symlink():
                    continue
                try:
                    resolved = path.resolve(strict=True)
                    if not resolved.is_relative_to(root) or not resolved.is_file():
                        continue
                    stat = resolved.stat()
                except OSError:
                    continue
                label = str(path.relative_to(root))
                records.append({'id': hashlib.sha256(label.encode()).hexdigest(),
                                'name': label, 'bytes': stat.st_size,
                                'modified': stat.st_mtime,
                                'importable': 0 < stat.st_size <= MAX_FILE_BYTES})
                if len(records) >= 500:
                    truncated = True
                    break
            if truncated or scanned >= MAX_SCAN_ENTRIES:
                truncated = True
                break
    except OSError:
        _error('Cannot read the server folder. Check mount permissions.', 503)
    return root, records, truncated


@router.get('/folder')
def list_folder():
    _, records, truncated = folder_entries()
    return {'files': sorted(records, key=lambda r: r['modified'], reverse=True),
            'truncated': truncated, 'label': 'Configured server TLE folder'}


def import_folder_files(data, data_root):
    ids = data.get('files')
    if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(v, str) for v in ids):
        _error('Select between 1 and 100 server files.')
    root, rows, _ = folder_entries()
    available = {r['id']: r for r in rows}
    blocks = []
    names = []
    total = 0
    for key in dict.fromkeys(ids):
        record = available.get(key)
        if not record or not record['importable']:
            _error('A selected file is unavailable, empty or larger than 10 MiB.')
        path = root / record['name']
        try:
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
                _error('Selected file is outside the import folder.', 403)
            with path.open('rb') as stream:
                raw = stream.read(MAX_FILE_BYTES+1)
            total += len(raw)
            if total > MAX_FILE_BYTES:
                _error('Combined source exceeds 10 MiB. Import fewer files.', 413)
            blocks.append(raw.decode('utf-8-sig'))
            names.append(record['name'])
        except (OSError, UnicodeError):
            _error('A selected file could not be read as UTF-8. Check its permissions and encoding.')
    name = Path(names[0]).name if len(names) == 1 else f'Server folder — {len(names)} files'
    result = store_tle(data_root, '\n'.join(blocks), name, source='server-folder')
    return dict(result, files_imported=len(names))


@router.post('/folder/import')
async def import_folder(request: Request):
    data = await read_json(request)
    if not isinstance(data, dict) or set(data) != {'files'}:
        _error('Expected selected server file IDs.')
    return await run_in_threadpool(import_folder_files, data, service(request).root)


def fetch_remote(data, root):
    source_name = data.get('source')
    if source_name not in ('celestrak', 'space-track'):
        _error('Choose CelesTrak or Space-Track.')
    ids = data.get('satellites')
    library = LIBRARIES['satellites']()
    if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(v, str) or v not in library for v in ids):
        _error('Choose between 1 and 100 library satellites.')
    ids = list(dict.fromkeys(ids))
    if source_name == 'space-track':
        if not isinstance(data.get('username'), str) or not data['username'].strip() or len(data['username']) > 254:
            _error('Enter your Space-Track username.')
        if not isinstance(data.get('password'), str) or not data['password'] or len(data['password']) > 1024:
            _error('Enter your Space-Track password.')
    if not remote_slot.acquire(blocking=False):
        _error('Another TLE download is active. Try again when it finishes.', 429)
    source = None
    try:
        source = CelesTrakSource() if source_name == 'celestrak' else SpaceTrackSource(data['username'], data['password'])
        # Do not retain provider bodies/exceptions: login responses may echo data.
        try:
            result = source.fetch_tle_data(ids)
        except Exception:
            _error('TLE provider request failed. Check connectivity, provider availability and credentials. Space-Track requires all requested IDs to be returned.', 502)
        text = result['tle_data'] if isinstance(result, dict) else result
        name = ('CelesTrak' if source_name == 'celestrak' else 'Space-Track') + time.strftime(' %Y-%m-%d %H:%M UTC', time.gmtime())
        saved = store_tle(root, text, name, source=source_name)
        missing = [str(row['norad_id']) for row in result.get('failed', [])] if isinstance(result, dict) else []
        return dict(saved, requested=len(ids), missing_norad_ids=missing)
    finally:
        try:
            if source is not None:
                source.close()
        finally:
            if source is not None and source_name == 'space-track':
                source.password = ''
                source.username = ''
            data.pop('password', None)
            data.pop('username', None)
            remote_slot.release()



@router.post('/fetch')
async def fetch_tles(request: Request):
    data = await read_json(request, 32*1024)
    if not isinstance(data, dict) or set(data)-{'source','satellites','username','password'}:
        _error('Invalid TLE source request.')
    return await run_in_threadpool(fetch_remote, data, service(request).root)
