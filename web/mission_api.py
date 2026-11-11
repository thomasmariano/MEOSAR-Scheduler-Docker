"""Saved mission presets and the desktop's automatic per-satellite TLE selection."""
from pathlib import Path
from threading import Lock
from uuid import uuid4, UUID
import json

from fastapi import APIRouter, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from satellites.tle_manager import TLEManager
from .job_runner import _write_json, _stamp
from .scheduling_api import MissionRequest, read_json, service, store_tle, _error, LIBRARIES, _label

router = APIRouter(prefix='/api')
selection_lock = Lock()


class ServerSelection(TLEManager):
    def __init__(self, folder):
        # Do not run desktop initialization or migration against server storage.
        self.USER_TLE_DIRECTORY = Path(folder)

    def get_user_tle_files(self):
        files = sorted(self.USER_TLE_DIRECTORY.glob('*.tle'))
        if len(files)>200 or sum(p.stat().st_size for p in files)>100*1024*1024:
            raise ValueError('Automatic selection is limited to 200 files / 100 MiB. Choose a source explicitly.')
        return files


def automatic_selection(root, ids, when):
    if when.tzinfo is None:_error('Event time must include a timezone.')
    library=LIBRARIES['satellites']()
    if not isinstance(ids,list) or not 1<=len(ids)<=100 or any(not isinstance(n,str) or n not in library for n in ids):
        _error('Choose 1–100 configured satellites.')
    with selection_lock:
        try:
            info=ServerSelection(Path(root)/'tles').get_automatic_tle(ids, when)
        except (ValueError, FileNotFoundError):
            _error('No usable matching records, or automatic library limit exceeded (200 files / 100 MiB). Import TLEs or choose a source explicitly.')
        saved=store_tle(root,info['file'].read_text(), 'Automatic — nearest epochs to event', source='automatic')
        sources=[]
        for source in set(info.get('source_files',{}).values()):
            source=Path(source);metadata=Path(root)/'tles'/(source.stem+'.json')
            record=json.loads(metadata.read_text()) if metadata.exists() else {}
            sources.append(record.get('name',source.name))
        saved['source_files']=sorted(sources)
        _write_json(Path(root)/'tles'/(saved['id']+'.json'),saved)
    return dict(saved, missing_norad_ids=info['missing_satellites'],
                available_norad_ids=info['available_satellites'],
                maximum_epoch_difference_hours=info['event_difference_hours'],
                epochs=info['satellite_epochs'],
                selection='Desktop per-satellite nearest epoch to event')


@router.post('/tles/automatic')
async def choose_automatic(request:Request):
    from datetime import datetime
    data=await read_json(request)
    if not isinstance(data,dict) or set(data)!={'satellites','event_time'}:_error('Expected satellites and event_time.')
    try:when=datetime.fromisoformat(data['event_time'].replace('Z','+00:00'))
    except (TypeError,AttributeError,ValueError):_error('Invalid event time.')
    return await run_in_threadpool(automatic_selection,service(request).root,data['satellites'],when)


@router.get('/presets')
def list_presets(request:Request):
    rows=[]
    for path in (service(request).root/'presets').glob('*.json'):
        try:
            record=json.loads(path.read_text())
            if not record.get('archived'):rows.append(record)
        except (OSError,ValueError):continue
    return sorted(rows,key=lambda r:r['saved_at'],reverse=True)


@router.post('/presets')
async def save_preset(request:Request):
    data=await read_json(request)
    try:mission=MissionRequest.model_validate(data)
    except ValidationError:_error('Preset must contain valid mission fields and resource selections.')
    if mission.event_time.tzinfo is None:_error('Event time must include a timezone.')
    if not _label(mission.mission_name):_error('Enter a nonempty mission name.')
    folder=service(request).root/'presets';folder.mkdir(exist_ok=True)
    record=dict(id=str(uuid4()),saved_at=_stamp(),mission=mission.model_dump())
    _write_json(folder/(record['id']+'.json'),record)
    with operations_lock:
        target=service(request).root/'operations.json'
        rows=json.loads(target.read_text()) if target.exists() else []
        rows.insert(0,dict(id=str(uuid4()),title=('Calendar event: '+mission.mission_name)[:100],
            message=f'{mission.event_type} · {mission.event_time.isoformat()} · {mission.ground_station} / {mission.mission_location}',
            notes='A mission was added to the shared calendar. Open Missions & calendar to review or load its inputs.',
            category='Event',created_at=_stamp(),resolved_at=None,availability_change=None,preset_id=record['id']))
        _write_json(target,rows[:500])
    return record


@router.post('/presets/{preset_id}/archive')
async def archive_preset(preset_id:str,request:Request):
    await read_json(request)
    try:
        if str(UUID(preset_id))!=preset_id:raise ValueError()
    except ValueError:_error('Preset not found.',404)
    path=service(request).root/'presets'/(preset_id+'.json')
    if not path.is_file():_error('Preset not found.',404)
    record=json.loads(path.read_text());record['archived']=True;_write_json(path,record)
    with operations_lock:
        notices=service(request).root/'operations.json'
        if notices.exists():
            rows=json.loads(notices.read_text())
            for row in rows:
                if row.get('preset_id')==preset_id:row['resolved_at']=_stamp()
            _write_json(notices,rows)
    return {'archived':True}


operations_lock = Lock()


@router.get('/operations')
def operations(request: Request):
    path=service(request).root/'operations.json'
    with operations_lock:
        return json.loads(path.read_text()) if path.exists() else []


@router.post('/operations')
async def update_operations(request: Request):
    """Shared LAN notices; availability changes affect future calculations only."""
    from .scheduling_api import library_lock, save_json, library_revision
    data=await read_json(request)
    if not isinstance(data,dict):_error('Expected an operations update.')
    with operations_lock:
        path=service(request).root/'operations.json'
        rows=json.loads(path.read_text()) if path.exists() else []
        if data.get('action')=='clear':
            if data!={'action':'clear','confirm':True}:_error('Confirm clearing notifications.')
            rows=[]
        elif data.get('action')=='delete':
            if set(data)!={'action','id'}:_error('Invalid notice deletion.')
            if not any(r['id']==data['id'] for r in rows):_error('Notice not found.',404)
            rows=[r for r in rows if r['id']!=data['id']]
        elif data.get('action')=='resolve':
            if set(data)!={'action','id'}:_error('Invalid notice update.')
            found=next((r for r in rows if r['id']==data['id']),None)
            if not found:_error('Notice not found.',404)
            found['resolved_at']=_stamp()
        else:
            if set(data)-{'title','message','notes','category','antenna','operational','revision'} or not {'title','message','category','antenna','operational','revision'}<=set(data):_error('Invalid operations update.')
            if not _label(data['title']) or not isinstance(data['message'],str) or len(data['message'])>2000:_error('Use a title and a message up to 2000 characters.')
            if not isinstance(data.get('notes',''),str) or len(data.get('notes',''))>4000:_error('Notes must be at most 4000 characters.')
            if data['category'] not in {'General','Antenna','Satellite','Event','TLE','Update'}:_error('Invalid notice category.')
            if not isinstance(data['antenna'],str):_error('Invalid antenna.')
            change=None
            if data['antenna']:
                if type(data['operational']) is not bool:_error('Choose an antenna availability state.')
                with library_lock:
                    library=LIBRARIES['antennas']()
                    if data['revision']!=library_revision(library):_error('Antenna library changed. Reopen the board and try again.',409)
                    if data['antenna'] not in library:_error('Antenna not found.')
                    library[data['antenna']]['operational']=data['operational']
                    save_json('antennas.json',library)
                    change={'antenna':data['antenna'],'operational':data['operational']}
            rows.insert(0,dict(id=str(uuid4()),title=data['title'].strip(),message=data['message'].strip(),notes=data.get('notes','').strip(),category=data['category'],created_at=_stamp(),resolved_at=None,availability_change=change))
            rows=rows[:500]
        _write_json(path,rows)
    return rows
