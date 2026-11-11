"""Load existing desktop schedule exports into isolated browser jobs."""
from datetime import timedelta
from dataclasses import replace
import csv
import io
import json
import re

from fastapi import APIRouter, Request
from pydantic import ValidationError
from core.schedule_editing import utc
from simulation.schedule_parser import parse_schedule_text
from .scheduling_api import MissionRequest, LIBRARIES, read_json, _error, _label

router=APIRouter(prefix='/api/schedules')


def parse_input(text,name):
    if not isinstance(text,str) or not text.strip() or len(text.encode())>1024*1024:
        _error('Schedule must be nonempty and at most 1 MiB.')
    if not _label(name):_error('Invalid schedule filename.')
    if text.lstrip('\ufeff \t\r\n').startswith(('{','[')):
        try:
            data=json.loads(text)
            records=data.get('schedule',data.get('assignments')) if isinstance(data,dict) else data
            if isinstance(records,dict):
                records=[dict(item,antenna=antenna) for antenna,rows in records.items() for item in rows]
            if not isinstance(records,list) or not 1<=len(records)<=2000:raise ValueError()
            out=io.StringIO();writer=csv.writer(out)
            for row in records:
                writer.writerow([row.get('norad_id',row.get('satellite_id','')),
                    row.get('meolut',row.get('field_2',2)),row.get('antenna',row.get('field_3','')),
                    utc(row['start']).strftime('%m/%d/%Y %H:%M:%S'),utc(row['end']).strftime('%m/%d/%Y %H:%M:%S')])
            text=out.getvalue()
        except (ValueError,KeyError,TypeError,AttributeError):
            _error('JSON must contain an assignment list or schedule grouped by antenna, with NORAD IDs and full UTC times.')
    try:parsed=parse_schedule_text(text,source=name)
    except ValueError as exc:_error(str(exc)[:4000])
    if len(parsed.assignments)>2000:_error('Import at most 2,000 assignments.')
    parsed.assignments=[replace(row,satellite_id=str(int(row.satellite_id)) if row.satellite_id.isdigit() else row.satellite_id) for row in parsed.assignments]
    return parsed


def resource_matches(resource,antennas):
    if resource in antennas:return [resource]
    return [name for name in antennas if ''.join(c for c in name if c.isdigit())==resource]


def normalize_imported(imported,entry,libraries):
    parsed=parse_input(imported['text'],imported['name']);mapping=imported.get('antenna_map')
    if not isinstance(mapping,dict) or set(mapping)!=set(parsed.resource_ids):_error('Map every schedule antenna ID explicitly.')
    start=entry.event_time-timedelta(hours=entry.hours_before)
    end=entry.event_time+timedelta(hours=entry.hours_after)
    rows=[]
    for item in parsed.assignments:
        key=str(int(item.satellite_id)) if item.satellite_id.isdigit() else item.satellite_id
        if key not in libraries['satellites'] or key not in entry.satellites:_error('Configure every imported NORAD ID in the satellite library first.')
        name=mapping[item.field_3]
        if not isinstance(name,str) or name not in entry.antennas:_error('Choose configured operational antennas for all resource IDs.')
        if not re.fullmatch('[0-9]{1,6}',item.field_2):_error('MEOLUT IDs must be numeric.')
        left,right=utc(item.start),utc(item.end)
        if not start<=left<right<=end:_error('The mission tracking window must contain all imported assignments. Adjust the form or load metadata first.')
        satellite=libraries['satellites'][key]
        rows.append(dict(antenna=name,norad_id=key,meosar_id=satellite['meosar_id'],band=satellite['band'],
                         meolut=item.field_2,start=left,end=right))
    return dict(source=parsed.source,assignments=rows,warnings=parsed.warnings)


@router.post('/inspect')
async def inspect_schedule(request:Request):
    data=await read_json(request)
    if not isinstance(data,dict) or set(data)!={'text','name'}:_error('Expected schedule text and filename.')
    parsed=parse_input(data['text'],data['name']);library=LIBRARIES['satellites']();antennas=LIBRARIES['antennas']()
    operational={name:record for name,record in antennas.items() if record.get('operational')}
    return dict(assignment_count=len(parsed.assignments),start=utc(parsed.start),end=utc(parsed.end),
                satellites=parsed.satellite_ids,missing_library_ids=[n for n in parsed.satellite_ids if n not in library],
                resources=[dict(id=r,matches=resource_matches(r,operational)) for r in parsed.resource_ids],
                operational_antennas=list(operational),warnings=parsed.warnings)


@router.post('/import',status_code=202)
async def import_schedule(request:Request):
    from .scheduling_api import queue_mission
    data=await read_json(request)
    if not isinstance(data,dict) or set(data)!={'mission','text','name','antenna_map'}:_error('Invalid schedule import request.')
    parsed=parse_input(data['text'],data['name'])
    if not isinstance(data['mission'],dict):_error('Configure the mission first.')
    mapping=data['antenna_map']
    if not isinstance(mapping,dict) or any(not isinstance(v,str) for v in mapping.values()):_error('Choose antenna mappings.')
    mission=dict(data['mission'],satellites=parsed.satellite_ids,antennas=list(dict.fromkeys(mapping.values())))
    try:entry=MissionRequest.model_validate(mission)
    except ValidationError:_error('Set valid mission inputs, tracking window, locations and TLE source before importing.')
    imported={key:data[key] for key in ('text','name','antenna_map')}
    return await queue_mission(request,entry,imported)
