"""Shared monitoring library and immutable TLE replay jobs for browser simulation."""
from copy import deepcopy
from pathlib import Path
from threading import Lock
import json
import re

from fastapi import APIRouter, Request
from .scheduling_api import read_json, service, find_job, _error, _label, validate_library, library_revision
from .simulator_api import frozen_result
from .job_runner import _write_json

router=APIRouter(prefix='/api')
monitor_lock=Lock()


def monitoring_snapshot(root):
    path=Path(root)/'monitoring-locations.json'
    records=json.loads(path.read_text()) if path.exists() else {}
    return dict(records=records,revision=library_revision(records))


@router.get('/monitoring-locations')
def monitoring_library(request:Request):
    with monitor_lock:return monitoring_snapshot(service(request).root)


@router.post('/monitoring-locations')
async def change_monitoring_location(request:Request):
    data=await read_json(request)
    if not isinstance(data,dict) or set(data)-{'revision','action','original','name','location'}:
        _error('Invalid monitoring-location update.')
    root=service(request).root
    with monitor_lock:
        snapshot=monitoring_snapshot(root)
        if data.get('revision')!=snapshot['revision']:_error('The monitoring library changed. Reopen this window before saving.',409)
        records=snapshot['records'];original=data.get('original')
        if original is not None and (not isinstance(original,str) or original not in records):_error('Monitoring location no longer exists.',409)
        if data.get('action')=='delete':
            if original is None:_error('Choose a location to delete.')
            del records[original]
        elif data.get('action')=='save':
            name=data.get('name')
            if not _label(name):_error('Enter a valid location name.')
            if name!=original and name in records:_error('A monitoring location already has that name.',409)
            record=validate_library('locations',{name:data.get('location')})[name]
            if original is not None:del records[original]
            records[name]=record
            if len(records)>1000:_error('Monitoring library is limited to 1,000 locations.')
        else:_error('Choose save or delete.')
        _write_json(Path(root)/'monitoring-locations.json',records)
        return dict(records=records,revision=library_revision(records))


@router.post('/jobs/{job_id}/replay',status_code=202)
async def replay_tle(job_id:str,request:Request):
    data=await read_json(request)
    if not isinstance(data,dict) or set(data)!={'tle_id','revision'}:_error('Choose a TLE source and schedule revision.')
    identifier=data['tle_id']
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{64}',identifier):_error('Choose a saved TLE source.')
    if not isinstance(data['revision'],str):_error('Choose a saved schedule revision.')
    path=find_job(request,job_id)
    result,original=frozen_result(path,data['revision'])
    source=service(request).root/'tles'/(identifier+'.tle')
    if not source.is_file():_error('TLE source no longer exists.',404)
    # Reuse the parent job's resource snapshots, not today's changed libraries.
    libraries={name:json.loads((path/'config'/(name+'.json')).read_text()) for name in ('locations','satellites','antennas')}
    mission=deepcopy(original)
    suffix=' · TLE replay'
    mission['mission_name']=original['mission_name'][:100-len(suffix)]+suffix
    mission['tle_source_id']=identifier
    mission['imported_schedule']=dict(source='TLE replay of '+job_id, warnings=['Assignments preserved for comparison against a different TLE source.'],
        assignments=[dict(row,antenna=name) for name,rows in result['schedule'].items() for row in rows])
    # An empty imported assignment set is valid for a replay of an idle mission.
    child=service(request).submit(mission,libraries,source.read_text(encoding='utf-8'))
    return dict(id=child,state='queued',parent_job_id=job_id)
