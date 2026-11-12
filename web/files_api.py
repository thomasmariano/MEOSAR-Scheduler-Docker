"""Explicit schedule exports and read-only browsing of published files."""
from pathlib import Path
from fastapi import APIRouter, Request, Query
from fastapi.responses import FileResponse, Response
import hashlib
import io
import os
import zipfile

from .scheduling_api import find_job, service, _error
from .simulator_api import frozen_result
from .export_names import export_basename

router = APIRouter(prefix='/api')


def schedule_export(request, job_id, revision):
    path = find_job(request, job_id)
    result, mission = frozen_result(path, revision)
    if not any(result.get('schedule', {}).values()):
        _error('This schedule has no assignments to export.')
    folder = path/'exports' if revision == 'original' else path/'edits'/revision
    if not (folder/'schedule.txt').is_file() or not (folder/'schedule.metadata.json').is_file():
        _error('Schedule export files are unavailable.', 404)
    return path, folder, export_basename(result, mission, revision)


@router.get('/jobs/{job_id}/export-info')
def export_info(job_id: str, request: Request, revision: str = 'original'):
    path, folder, name = schedule_export(request, job_id, revision)
    return dict(revision=revision, filename=name+'.txt', metadata_filename=name+'.metadata.json',
                bundle_filename=name+'.zip', tle_available=(path/'input.tle').is_file())


@router.get('/jobs/{job_id}/export')
def export_schedule(job_id: str, request: Request, revision: str = 'original',
                    format: str = Query('txt', pattern='^(txt|metadata|zip)$'), include_tle: bool = True):
    path, folder, name = schedule_export(request, job_id, revision)
    if format == 'txt':
        return FileResponse(folder/'schedule.txt', filename=name+'.txt', media_type='text/plain')
    if format == 'metadata':
        return FileResponse(folder/'schedule.metadata.json', filename=name+'.metadata.json', media_type='application/json')
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(folder/'schedule.txt', name+'.txt')
        bundle.write(folder/'schedule.metadata.json', name+'.metadata.json')
        if include_tle and (path/'input.tle').is_file():
            bundle.write(path/'input.tle', name+'.tle')
        bundle.writestr('READ ME.txt', 'Extract these files together. The TXT is the machine-readable tracking schedule; keep its matching .metadata.json beside it for desktop simulator loading. In the web app, use Load existing mission and optionally choose the metadata file. Import the bundled TLE first if included, select that source and review antenna mappings before loading. All schedule times are UTC. Original and edited schedules are separate exports.\n')
    # Let Starlette generate safe UTF-8 Content-Disposition, including non-ASCII names.
    disposition = FileResponse(folder/'schedule.txt', filename=name+'.zip').headers['content-disposition']
    return Response(output.getvalue(), media_type='application/zip', headers={'Content-Disposition': disposition})


ALLOWED = {'.txt', '.json', '.tle', '.3le', '.png', '.mp4', '.webm', '.zip'}


def library_records():
    rows = []
    count = 0
    for group, configured in [('Exports', os.environ.get('MEOSAR_EXPORT_DIRECTORY')), ('TLE Library', os.environ.get('MEOSAR_TLE_EXPORT_DIRECTORY'))]:
        if not configured:
            continue
        root = Path(configured).resolve()
        if not root.is_dir():
            continue
        # Only published files; never Application Data, certs or arbitrary host paths.
        for current, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(current)/d).is_symlink())
            for filename in sorted(names):
                count += 1
                if count > 10000:
                    return rows, True
                path = Path(current)/filename
                if filename.startswith('.') or path.suffix.lower() not in ALLOWED or path.is_symlink():
                    continue
                try:
                    resolved = path.resolve(strict=True)
                    if not resolved.is_relative_to(root) or not resolved.is_file():
                        continue
                    relative = str(path.relative_to(root))
                    identifier = hashlib.sha256((group+'/'+relative).encode()).hexdigest()
                    stat = resolved.stat()
                    rows.append(dict(id=identifier, name=filename, folder=group+('/'+str(path.parent.relative_to(root)) if path.parent!=root else ''),
                                     bytes=stat.st_size, modified=stat.st_mtime, path=resolved))
                except OSError:
                    continue
    return rows, False


@router.get('/files')
def browse_files():
    rows, limited = library_records()
    return dict(enabled=bool(os.environ.get('MEOSAR_EXPORT_DIRECTORY') or os.environ.get('MEOSAR_TLE_EXPORT_DIRECTORY')),
                files=[{k:v for k,v in row.items() if k != 'path'} for row in rows], truncated=limited)


@router.get('/files/{identifier}')
def download_library_file(identifier: str):
    rows, _ = library_records()
    row = next((r for r in rows if r['id'] == identifier), None)
    if row is None:
        _error('Published file not found. Refresh the file library.', 404)
    return FileResponse(row['path'], filename=row['name'])
