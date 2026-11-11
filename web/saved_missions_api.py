"""Named durable snapshots of completed schedules, independent of edit history."""
from pathlib import Path
from uuid import uuid4,UUID
import json
import shutil

from fastapi import APIRouter,Request
from fastapi.responses import FileResponse
from .scheduling_api import read_json,find_job,service,_error,_label
from .simulator_api import frozen_result
from .job_runner import _write_json,_stamp

router=APIRouter(prefix='/api/saved-missions')
FILES={'result.json','schedule.txt','schedule.metadata.json','tracking_schedule.png','satellite_coverage_timeline.png','all_satellite_coverage.png'}


def saved_path(request,identifier):
    try:
        if str(UUID(identifier))!=identifier:raise ValueError()
    except (ValueError,AttributeError):_error('Saved mission not found.',404)
    path=service(request).root/'saved-missions'/identifier
    if not (path/'saved.json').is_file():_error('Saved mission not found.',404)
    return path


@router.get('')
def saved_missions(request:Request):
    rows=[]
    for path in (service(request).root/'saved-missions').glob('*/saved.json'):
        try:rows.append(json.loads(path.read_text()))
        except (OSError,ValueError):continue
    return sorted(rows,key=lambda row:row['saved_at'],reverse=True)


@router.post('')
async def save_mission(request:Request):
    data=await read_json(request)
    if not isinstance(data,dict) or set(data)!={'job_id','revision','name'} or not _label(data['name']):_error('Provide a saved schedule name, job and revision.')
    if not isinstance(data['job_id'],str) or not isinstance(data['revision'],str):_error('Invalid schedule reference.')
    path=find_job(request,data['job_id']);result,mission=frozen_result(path,data['revision'])
    source=path if data['revision']=='original' else path/'edits'/data['revision']
    target=service(request).root/'saved-missions'/str(uuid4());target.mkdir(parents=True)
    try:
        _write_json(target/'result.json',result)
        for name in FILES-{'result.json'}:
            original=path/'graphs'/name if name.endswith('.png') else path/'exports'/name
            if data['revision']!='original' and name in {'schedule.txt','schedule.metadata.json','tracking_schedule.png'}:original=source/name
            if original.is_file():shutil.copyfile(original,target/name)
        _write_json(target/'mission.json',mission)
        shutil.copytree(path/'config',target/'config');shutil.copyfile(path/'input.tle',target/'input.tle')
        record=dict(id=target.name,name=data['name'].strip(),job_id=data['job_id'],revision=data['revision'],saved_at=_stamp(),
            event_time=mission['event_time'],event_type=mission['event_type'],mission_location=mission['mission_location'],ground_station=mission['ground_station'],
            assignment_count=sum(len(v) for v in result['schedule'].values()))
        # A saved bookmark keeps its originating revision usable in the simulator.
        from .schedule_editing_api import edit_lock
        with edit_lock:
            retained=path/'retained-revisions.json';values=json.loads(retained.read_text()) if retained.exists() else []
            if data['revision'] not in values:values.append(data['revision']);_write_json(retained,values)
        _write_json(target/'saved.json',record)
        return record
    except Exception:shutil.rmtree(target,ignore_errors=True);raise


@router.get('/{identifier}')
def saved_details(identifier:str,request:Request):
    path=saved_path(request,identifier);value=json.loads((path/'saved.json').read_text());value['files']=sorted(p.name for p in path.iterdir() if p.is_file() and p.name in FILES);return value


@router.get('/{identifier}/files/{name}')
def saved_file(identifier:str,name:str,request:Request,inline:bool=False):
    if name not in FILES:_error('File not found.',404)
    path=saved_path(request,identifier)/name
    if not path.is_file():_error('File not found.',404)
    return FileResponse(path,filename=None if inline and name.endswith('.png') else name,
        media_type='image/png' if name.endswith('.png') else 'application/json' if name.endswith('.json') else 'text/plain')
