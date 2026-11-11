"""Internal job boundary for the shared scheduler; not a browser API.

prepare_job snapshots inputs. run_job launches a fresh headless process so its
configuration, Matplotlib state and outputs cannot collide with another job.
The browser API supplies a bounded queue and validated upload handling.
"""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4, UUID
import csv
import time
import hashlib
import json
import os
import subprocess
import sys
import tempfile

MAX_TLE_BYTES = 20 * 1024 * 1024


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, 'item'):
        return value.item()
    raise TypeError(f'Unsupported result type: {type(value).__name__}')


def _write_json(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.'+path.name, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, default=_json_default, indent=2, allow_nan=False)
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _job_path(root, job_id):
    canonical = str(UUID(str(job_id)))
    if canonical != str(job_id):
        raise ValueError('Invalid canonical job ID.')
    return Path(root).resolve() / 'jobs' / canonical


def prepare_job(data_root, mission, libraries, tle_text):
    """Called internally with already authorized data; returns a UUID, not paths.

    Snapshot libraries keys: locations, antennas, satellites. No credentials or
    user-supplied server paths are accepted in the mission configuration.
    """
    if not isinstance(tle_text, str) or not tle_text.strip() or len(tle_text.encode('utf-8')) > MAX_TLE_BYTES:
        raise ValueError('TLE text must be nonempty and at most 20 MiB.')
    allowed = {'mission_name', 'mission_location', 'ground_station', 'hours_before',
               'hours_after', 'event_time', 'satellites', 'antennas', 'event_type',
               'mission_type', 'scheduling_strategy', 'imported_schedule', 'tle_source_id'}
    unknown = set(mission) - allowed
    if unknown:
        raise ValueError('Unexpected mission fields: ' + ', '.join(sorted(unknown)))
    event = mission.get('event_time')
    if isinstance(event, str):
        event = datetime.fromisoformat(event.replace('Z', '+00:00'))
    if not isinstance(event, datetime) or event.tzinfo is None:
        raise ValueError('Event time must include a timezone.')
    config = dict(mission, event_time=event.astimezone(timezone.utc))
    for name in ('locations', 'antennas', 'satellites'):
        if not isinstance(libraries.get(name), dict):
            raise ValueError(f'{name} library must be an object.')
    job_id = str(uuid4())
    path = _job_path(data_root, job_id)
    path.mkdir(parents=True, exist_ok=False)
    (path/'config').mkdir()
    try:
        _write_json(path/'mission.json', config)
        for name in ('locations', 'antennas', 'satellites'):
            _write_json(path/'config'/f'{name}.json', libraries[name])
        (path/'input.tle').write_text(tle_text, encoding='utf-8')
        inputs = ['mission.json', 'input.tle', 'config/locations.json', 'config/antennas.json', 'config/satellites.json']
        manifest = {name: hashlib.sha256((path/name).read_bytes()).hexdigest() for name in inputs}
        _write_json(path/'manifest.json', manifest)
        _write_json(path/'status.json', dict(id=job_id, state='prepared', created_at=_stamp()))
    except Exception:
        _write_json(path/'status.json', dict(id=job_id, state='failed', message='Input snapshot could not be created.'))
        raise
    return job_id


def run_job(data_root, job_id, timeout_seconds=1800, cancel_event=None):
    """Blocking executor called by the single background queue worker.

    Fresh workers must be launched by this function, not imported into the web
    process. A job cannot be executed twice, even after failure.
    """
    path = _job_path(data_root, job_id)
    if not (path/'manifest.json').is_file():
        raise FileNotFoundError('Prepared job not found.')
    lock = path/'run.lock'
    with lock.open('x') as stream:
        stream.write(_stamp())
    env = dict(os.environ, MPLBACKEND='Agg',
               MEOSAR_CONFIG_DIR=str(path/'config'), MEOSAR_TLE_DIR=str(path/'tle-cache'),
               MPLCONFIGDIR=str(path/'matplotlib-cache'))
    _write_json(path/'status.json', dict(id=job_id, state='running', started_at=_stamp()))
    with (path/'worker.log').open('wb') as log:
        try:
            process = subprocess.Popen([sys.executable, '-m', 'web.job_runner', '--worker', str(path)],
                                       cwd=Path(__file__).resolve().parent.parent, env=env,
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + timeout_seconds
            reason = None
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    reason = 'cancelled'
                elif time.monotonic() >= deadline:
                    reason = 'timeout'
                if reason:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    break
                time.sleep(.2)
            if reason or process.returncode:
                _write_json(path/'status.json', dict(id=job_id,
                            state='cancelled' if reason == 'cancelled' else 'failed', finished_at=_stamp(),
                            message='Calculation cancelled.' if reason == 'cancelled' else
                            'Calculation exceeded the job time limit.' if reason == 'timeout' else
                            'Calculation failed; see the server-side worker log.'))
        except Exception:
            _write_json(path/'status.json', dict(id=job_id, state='failed', finished_at=_stamp(),
                        message='Worker could not start.'))
            raise
    return json.loads((path/'status.json').read_text(encoding='utf-8'))


def _worker(path):
    # Configure before importing any scientific/controller code.
    path = Path(path).resolve()
    os.environ['MPLBACKEND'] = 'Agg'
    os.environ['MEOSAR_CONFIG_DIR'] = str(path/'config')
    os.environ['MEOSAR_TLE_DIR'] = str(path/'tle-cache')
    os.environ['MPLCONFIGDIR'] = str(path/'matplotlib-cache')
    manifest = json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    expected = {'mission.json', 'input.tle', 'config/locations.json', 'config/antennas.json', 'config/satellites.json'}
    if set(manifest) != expected:
        raise ValueError('Unexpected input manifest.')
    for name, digest in manifest.items():
        if hashlib.sha256((path/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Job inputs changed after preparation.')
    config = json.loads((path/'mission.json').read_text(encoding='utf-8'))
    config['event_time'] = datetime.fromisoformat(config['event_time'])
    config['tle_file'] = str(path/'input.tle')
    imported=config.pop('imported_schedule',None)
    from scheduler.scheduler_controller import SchedulerController
    results = SchedulerController().run(config, output_directory=path/'graphs')
    if imported is not None:
        from core.schedule_editing import normalize,validate,utc
        from core.schedule_diagnostics import analyze_schedule
        from graphs.schedule_graph import generate_schedule_graph
        context=dict(start=results['tracking_start'],end=results['tracking_end'],
            antennas=config['antennas'],visibility=results['visibility'],minimum_seconds=600,
            satellites=[dict(norad_id=str(s.model.satnum),meosar_id=str(s.meosar_id),band=s.band) for s in results['satellites']])
        assignments=normalize(imported['assignments'],context)
        grouped={}
        for row in assignments:grouped.setdefault(row['antenna'],[]).append(row)
        results['schedule']=grouped
        report=analyze_schedule([],grouped,context['start'],context['end'])
        results['schedule_diagnostics']={key:report[key] for key in ('below_three_minutes','below_three_intervals','minimum_assigned_satellites','handoffs_by_antenna','final_antenna_minutes')}
        results['schedule_diagnostics']['source']='Imported assignments; not generated allocations.'
        results['import_warnings']=imported['warnings']
        results['import_validation_errors']=validate(assignments,context)
        results['import_source']=imported['source']
        results['schedule_graph']=generate_schedule_graph(grouped,mission_name=config['mission_name'],
            event_time=config['event_time'],event_type=config['event_type'],mission_start=context['start'],mission_end=context['end'],
            ground_station_location=config['ground_station'],landing_site_location=config['mission_location'],output_directory=path/'graphs')
    # Keep Skyfield objects and machine-local paths out of downloadable results.
    summary = {key: results[key] for key in ('schedule', 'visibility', 'tracking_start',
        'tracking_end', 'event_time', 'selection_audit', 'schedule_diagnostics', 'scheduling_strategy',
        'import_warnings','import_validation_errors','import_source') if key in results}
    summary['graphs'] = {name: 'graphs/'+Path(results[name]).name
                         for name in ('graph_file', 'all_graph_file', 'schedule_graph')}
    exports = path/'exports'
    exports.mkdir(exist_ok=True)
    with (exports/'schedule.txt').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        for antenna, tracks in sorted(results['schedule'].items()):
            number = ''.join(c for c in str(antenna) if c.isdigit()) or str(antenna)
            for track in sorted(tracks, key=lambda t: t['start']):
                writer.writerow([track['norad_id'], track.get('meolut',2), number,
                                 track['start'].astimezone(timezone.utc).strftime('%m/%d/%Y %H:%M:%S'),
                                 track['end'].astimezone(timezone.utc).strftime('%m/%d/%Y %H:%M:%S')])
            if tracks:
                stream.write('\n')
    locations = json.loads((path/'config/locations.json').read_text())
    _write_json(exports/'schedule.metadata.json', {
        'metadata_version': 1,
        'mission': {'name': config['mission_name'], 'type': config['event_type'],
                    'event_time': config['event_time']},
        'mission_site': dict(name=config['mission_location'], **locations[config['mission_location']]),
        'ground_station': dict(name=config['ground_station'], **locations[config['ground_station']]),
        'schedule': {
            'assignment_count': sum(len(v) for v in results['schedule'].values()),
            'start': min((t['start'] for v in results['schedule'].values() for t in v), default=None),
            'end': max((t['end'] for v in results['schedule'].values() for t in v), default=None),
            'time_format': 'UTC'},
        'scheduling_strategy': results.get('scheduling_strategy', {})})
    _write_json(path/'result.json', summary)
    _write_json(path/'status.json', dict(id=path.name, state='completed', finished_at=_stamp(),message=('Imported schedule loaded; review assignment validation in the editor.' if imported is not None else 'Calculation completed.')))


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--worker':
        raise SystemExit('Internal worker. Use prepare_job/run_job from server code; do not pass browser paths.')
    _worker(sys.argv[2])
