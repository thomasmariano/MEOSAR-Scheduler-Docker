"""Validated edit revisions for completed jobs; original outputs stay immutable."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4
import csv
import json
import os
import re
import shutil
import subprocess
import sys

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from core.schedule_editing import utc, normalize, validate, opportunities
from core.schedule_diagnostics import analyze_schedule
from .scheduling_api import find_job, read_json, _error
from .job_runner import _write_json

router = APIRouter(prefix='/api/jobs')
edit_lock = Lock()
FILES = {'schedule.txt', 'schedule.metadata.json', 'tracking_schedule.png', 'result.json'}


def load_context(path):
    if json.loads((path/'status.json').read_text()).get('state') != 'completed':
        _error('Complete the calculation before editing.', 409)
    result = json.loads((path/'result.json').read_text())
    mission = json.loads((path/'mission.json').read_text())
    library = json.loads((path/'config/satellites.json').read_text())
    used = set(result.get('selection_audit', {}).get('used_norad_ids', mission['satellites']))
    context = dict(start=utc(result['tracking_start']), end=utc(result['tracking_end']),
                   antennas=mission['antennas'], minimum_seconds=600,
                   candidate_satellites=[dict(norad_id=n, **library[n]) for n in mission['satellites']],
                   satellites=[dict(norad_id=n, **library[n]) for n in mission['satellites'] if n in used],
                   visibility=result['visibility'])
    return context, result, mission


def state_for(path):
    target = path/'editor.json'
    return json.loads(target.read_text()) if target.exists() else {'version': 0, 'history': ['original'], 'position': 0}


def schedule_for(path, state, context, result):
    revision = state['history'][state['position']]
    source = result if revision == 'original' else json.loads((path/'edits'/revision/'result.json').read_text())
    return normalize(source['schedule'], context)


def assignment_quality(items,context):
    grouped={}
    for item in items:grouped.setdefault(item['antenna'],[]).append(item)
    quality=analyze_schedule([],grouped,context['start'],context['end'])
    return {key:quality[key] for key in ('below_three_minutes','below_three_intervals',
        'minimum_assigned_satellites','handoffs_by_antenna','final_antenna_minutes')}


def response_for(path):
    context, result, mission = load_context(path)
    state = state_for(path)
    schedule = schedule_for(path, state, context, result)
    revision = state['history'][state['position']]
    return dict(version=state['version'], revision=revision, schedule=schedule,
                antennas=context['antennas'], satellites=context['satellites'], start=context['start'], end=context['end'],
                can_undo=state['position'] > 0, can_redo=state['position']+1 < len(state['history']),
                validation_errors=validate(schedule, context), quality=assignment_quality(schedule,context),
                downloads=[] if revision == 'original' else sorted(FILES))


def json_response(data):
    # FastAPI can serialize datetimes; keep the shared Python objects intact.
    return data


@router.get('/{job_id}/editor')
def editor(job_id: str, request: Request):
    path = find_job(request, job_id)
    with edit_lock:
        return json_response(response_for(path))


@router.get('/{job_id}/editor/opportunities')
def coverage(job_id: str, request: Request, antenna: str):
    path = find_job(request, job_id)
    with edit_lock:
        context, result, _ = load_context(path)
        if antenna not in context['antennas']:
            _error('Choose an antenna from this run.')
        state = state_for(path)
        rows = opportunities(context, schedule_for(path, state, context, result), antenna, include_rejected=True)
        return dict(version=state['version'], rows=rows)


def draft_items(records,context):
    """Derive identities/bands from the frozen library, never client labels."""
    if not isinstance(records,list) or len(records)>2000:_error('Draft must contain at most 2,000 assignments.')
    catalog={row['norad_id']:row for row in context.get('candidate_satellites',context['satellites'])}
    items=[]
    required={'antenna','norad_id','start','end'}
    for record in records:
        if not isinstance(record,dict) or not required<=set(record) or set(record)-required-{'meolut'}:
            _error('Each draft assignment needs antenna, NORAD ID and full UTC start/end times.')
        if any(not isinstance(record[key],str) for key in required):_error('Draft assignment fields must be text.')
        satellite=catalog.get(record['norad_id'])
        if not satellite:_error('Draft includes a satellite outside this job snapshot.')
        meolut=str(record.get('meolut','2'))
        if not re.fullmatch('[0-9]{1,6}',meolut):_error('MEOLUT IDs must be numeric.')
        try:
            left=datetime.fromisoformat(record['start'].replace('Z','+00:00'))
            right=datetime.fromisoformat(record['end'].replace('Z','+00:00'))
            if left.tzinfo is None or right.tzinfo is None:raise ValueError()
        except (ValueError,TypeError,AttributeError):_error('Draft timestamps must include a timezone.')
        items.append(dict(antenna=record['antenna'],norad_id=record['norad_id'],
            meosar_id=str(satellite['meosar_id']),band=satellite['band'],
            start=left,end=right,meolut=meolut))
    return normalize(items,context)


@router.post('/{job_id}/editor/draft')
async def check_draft(job_id:str,request:Request):
    data=await read_json(request)
    if not isinstance(data,dict) or set(data)-{'version','assignments','antenna'}:_error('Invalid draft review request.')
    path=find_job(request,job_id)
    with edit_lock:
        context,_,_=load_context(path);state=state_for(path)
        if type(data.get('version')) is not int or data['version']!=state['version']:
            _error('Saved schedule changed in another window. Your local draft is retained; reload before applying.',409)
        items=draft_items(data.get('assignments'),context)
        errors=validate(items,context)
        response=dict(version=state['version'],validation_errors=errors[:100],error_count=len(errors),quality=assignment_quality(items,context))
        if 'antenna' in data:
            antenna=data['antenna']
            if not isinstance(antenna,str) or antenna not in context['antennas']:_error('Choose an antenna from this run.')
            response['rows']=opportunities(context,items,antenna,include_rejected=True)
        return response


def apply_change(path, data):
    with edit_lock:
        context, result, mission = load_context(path)
        state = state_for(path)
        if type(data.get('version')) is not int or data['version'] != state['version']:
            _error('Schedule changed in another window. Reload the editor before saving.', 409)
        action = data.get('action')
        if action in ('undo', 'redo', 'reset'):
            if action == 'undo' and state['position'] > 0:
                state['position'] -= 1
            elif action == 'redo' and state['position']+1 < len(state['history']):
                state['position'] += 1
            elif action == 'reset':
                state['position'] = 0
            else:
                _error('No revision available for this action.', 409)
        else:
            items = schedule_for(path, state, context, result)
            index = data.get('index')
            if action in ('update', 'delete'):
                if type(index) is not int or not 0 <= index < len(items):
                    _error('Assignment no longer exists.', 409)
            if action == 'replace':
                items=draft_items(data.get('assignments'),context)
            elif action == 'delete':
                items.pop(index)
            elif action in ('add', 'update'):
                record = data.get('assignment')
                allowed = {'antenna', 'norad_id', 'start', 'end'}
                if not isinstance(record, dict) or set(record) != allowed:
                    _error('Provide antenna, NORAD ID, UTC start and UTC end.')
                if any(not isinstance(record[k], str) for k in allowed):
                    _error('Assignment fields must be text values.')
                satellite = next((s for s in context['satellites'] if s['norad_id'] == record['norad_id']), None)
                if not satellite:
                    _error('Satellite is not part of this calculation.')
                try:
                    left = datetime.fromisoformat(record['start'].replace('Z','+00:00'))
                    right = datetime.fromisoformat(record['end'].replace('Z','+00:00'))
                    if left.tzinfo is None or right.tzinfo is None:
                        raise ValueError()
                except (ValueError, TypeError, AttributeError):
                    _error('Enter full start/end timestamps with a timezone.')
                assignment = dict(antenna=record['antenna'], norad_id=satellite['norad_id'],
                                  meosar_id=satellite['meosar_id'], band=satellite['band'],
                                  start=left, end=right, meolut=items[index].get('meolut','2') if action=='update' else '2')
                if action == 'add':items.append(assignment)
                else:items[index] = assignment
            else:
                _error('Unknown editor action.')
            if len(items) > 2000:_error('Schedule exceeds 2,000 assignments.')
            errors = validate(items, context)
            if errors:_error('\n'.join(errors[:30]))
            items = normalize(items, context)
            revision = str(uuid4())
            folder = path/'edits'/revision
            folder.mkdir(parents=True)
            try:
                revised = deepcopy(result)
                revised['schedule'] = {}
                for item in items:
                    revised['schedule'].setdefault(item['antenna'], []).append(item)
                revised['schedule_diagnostics'] = {
                    'notice': 'Original allocation diagnostics apply to the generated schedule only. This revision passed shared sampled-visibility edit validation.',
                    'assignment_count': len(items),**assignment_quality(items,context)}
                revised['graphs'] = {'schedule_graph': 'tracking_schedule.png'}
                revised['edit_revision'] = revision
                _write_json(folder/'result.json', revised)
                metadata = json.loads((path/'exports/schedule.metadata.json').read_text())
                metadata['schedule'] = dict(assignment_count=len(items),
                                            start=min((i['start'] for i in items), default=None),
                                            end=max((i['end'] for i in items), default=None), time_format='UTC')
                metadata['metadata_version'] = 1
                metadata.pop('version', None)
                metadata['edit_revision'] = revision
                _write_json(folder/'schedule.metadata.json', metadata)
                with (folder/'schedule.txt').open('w', encoding='utf-8', newline='') as stream:
                    writer = csv.writer(stream, lineterminator='\n')
                    previous = None
                    for item in items:
                        if previous is not None and previous != item['antenna']:stream.write('\n')
                        previous = item['antenna']
                        number = ''.join(c for c in item['antenna'] if c.isdigit()) or item['antenna']
                        writer.writerow([item['norad_id'], item.get('meolut',2), number,
                            item['start'].strftime('%m/%d/%Y %H:%M:%S'), item['end'].strftime('%m/%d/%Y %H:%M:%S')])
                env = dict(os.environ, MPLBACKEND='Agg', MPLCONFIGDIR=str(path/'matplotlib-cache'),
                           XDG_CACHE_HOME=str(path/'render-cache'))
                with (folder/'render.log').open('wb') as log:
                    process = subprocess.run([sys.executable, '-m', 'web.schedule_editing_api', str(path), revision],
                        cwd=Path(__file__).resolve().parent.parent, env=env,
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=120)
                if process.returncode or not (folder/'tracking_schedule.png').is_file():
                    raise RuntimeError('Render failed')
            except Exception:
                shutil.rmtree(folder, ignore_errors=True)
                _error('Could not render the edited schedule. The previous revision is unchanged.', 500)
            # Branching after undo drops redo from the history, but keeps disk artifacts.
            history = state['history'][:state['position']+1] + [revision]
            state['history'] = ['original'] + [r for r in history if r != 'original'][-49:]
            state['position'] = len(state['history'])-1
        state['version'] += 1
        _write_json(path/'editor.json', state)
        return response_for(path)


@router.post('/{job_id}/editor')
async def change_schedule(job_id: str, request: Request):
    data = await read_json(request)
    if not isinstance(data, dict) or set(data)-{'version','action','index','assignment','assignments'}:
        _error('Invalid edit request.')
    path = find_job(request, job_id)
    return await run_in_threadpool(apply_change, path, data)


@router.get('/{job_id}/editor/files/{revision}/{name}')
def edited_file(job_id: str, revision: str, name: str, request: Request, inline: bool=False):
    path = find_job(request, job_id)
    if name not in FILES:_error('File not found.',404)
    with edit_lock:
        state = state_for(path)
        retained=path/'retained-revisions.json'
        kept=json.loads(retained.read_text()) if retained.exists() else []
        if revision == 'original' or (revision not in state['history'] and revision not in kept):
            _error('Revision not found.',404)
        target = path/'edits'/revision/name
        if not target.is_file():_error('File not found.',404)
    download_name=name
    if name in {'schedule.txt','schedule.metadata.json'}:
        from .export_names import export_basename
        base=export_basename(json.loads((path/'edits'/revision/'result.json').read_text()),json.loads((path/'mission.json').read_text()),revision)
        download_name=base+('.txt' if name=='schedule.txt' else '.metadata.json')
    return FileResponse(target, filename=None if inline and name.endswith('.png') else download_name,
        media_type='image/png' if name.endswith('.png') else 'application/json' if name.endswith('.json') else 'text/plain')


def render_revision(path, revision):
    from graphs.schedule_graph import generate_schedule_graph
    folder = path/'edits'/revision
    result = json.loads((folder/'result.json').read_text())
    mission = json.loads((path/'mission.json').read_text())
    generate_schedule_graph(result['schedule'], mission_name=mission['mission_name'],
        event_time=utc(mission['event_time']), event_type=mission['event_type'],
        mission_start=utc(result['tracking_start']), mission_end=utc(result['tracking_end']),
        ground_station_location=mission['ground_station'], landing_site_location=mission['mission_location'],
        output_directory=folder)


if __name__ == '__main__':
    render_revision(Path(sys.argv[1]), sys.argv[2])
