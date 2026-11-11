"""Local-development scheduling API and bounded, single-worker queue.

This service intentionally has no network-user authentication. Keep Compose's
localhost binding until identity/access controls are implemented.
"""
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Event, BoundedSemaphore, Lock
import hashlib
import json
import logging
import math
import re
import tempfile

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from config.config_manager import load_locations, load_satellites, load_antennas, save_json
from .job_runner import prepare_job, run_job, _job_path, _write_json, _stamp

router = APIRouter(prefix='/api')
logger = logging.getLogger(__name__)
library_lock = Lock()
LIBRARIES = {'locations': load_locations, 'satellites': load_satellites, 'antennas': load_antennas}
DOWNLOADS = {'result.json', 'schedule.txt', 'schedule.metadata.json',
             'tracking_schedule.png', 'satellite_coverage_timeline.png', 'all_satellite_coverage.png'}


def _error(message, code=422):
    raise HTTPException(code, message)


async def read_json(request, limit=2*1024*1024):
    # Custom header + same-origin check prevents cross-origin form submissions.
    if request.headers.get('x-meosar-request') != '1':
        _error('This operation requires the MEOSAR browser client.', 403)
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        _error('Cross-origin writes are not permitted.', 403)
    if request.headers.get('content-type','').split(';')[0] != 'application/json':
        _error('Send application/json.', 415)
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks)>limit:_error('Upload is too large.', 413)
    try:
        return json.loads(chunks, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    except (ValueError, UnicodeDecodeError):
        _error('The request is not valid JSON.')


def _label(value):
    return isinstance(value,str) and 0<len(value.strip())<=100 and not any(ord(c)<32 for c in value)


def validate_library(kind, data):
    if not isinstance(data,dict) or len(data)>1000:_error('Library must be an object with at most 1,000 records.')
    result={};owners=set()
    for key,record in data.items():
        if not _label(key) or not isinstance(record,dict):_error('Each record needs a valid name/ID and object value.')
        if kind=='locations':
            try:lat,lon,height=(float(record[k]) for k in ('latitude','longitude','elevation'))
            except (KeyError,ValueError,TypeError):_error(f'{key}: latitude, longitude and elevation are required numbers.')
            if not all(math.isfinite(v) for v in (lat,lon,height)) or not -90<=lat<=90 or not -180<=lon<=180:_error(f'{key}: invalid coordinates.')
            result[key]=dict(latitude=lat,longitude=lon,elevation=height)
            if record.get('type') in ('ground_station','mission_site'):
                result[key]['type']=record['type']
        elif kind=='antennas':
            bands=record.get('bands');operational=record.get('operational')
            if type(operational) is not bool or not isinstance(bands,list) or not bands or any(b not in ('S','L') for b in bands):_error(f'{key}: operational must be true/false and bands must contain S and/or L.')
            result[key]=dict(operational=operational,bands=list(dict.fromkeys(bands)))
        else:
            meo=str(record.get('meosar_id',''));band=record.get('band');enabled=record.get('enabled')
            if not re.fullmatch(r'[0-9]{1,9}',key) or not re.fullmatch(r'11[34][0-9]{2}',meo):_error(f'{key}: use numeric NORAD and a 113xx/114xx MEOSAR ID.')
            identifier=str(int(key))
            if identifier in result or meo in owners:_error('Duplicate NORAD or MEOSAR identity.')
            if type(enabled) is not bool or band!=('S' if meo.startswith('113') else 'L'):_error(f'{key}: enabled must be true/false and band must match the MEOSAR family.')
            owners.add(meo);result[identifier]=dict(meosar_id=meo,band=band,enabled=enabled)
    return result


class AlternateLocation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    elevation: float = Field(allow_inf_nan=False, default=0)
    weight: float = Field(ge=.1, le=10, allow_inf_nan=False, default=1)


class CoverageStrategy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    geometry: bool = True
    locations: list[AlternateLocation] = Field(default_factory=list, max_length=20)


class MissionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mission_name: str=Field(min_length=1,max_length=100)
    event_type: str
    event_time: datetime
    hours_before: float=Field(ge=0,le=168+59/60,allow_inf_nan=False)
    hours_after: float=Field(ge=0,le=168+59/60,allow_inf_nan=False)
    ground_station: str
    mission_location: str
    satellites: list[str]=Field(min_length=1,max_length=100)
    antennas: list[str]=Field(min_length=1,max_length=50)
    tle_id: str
    scheduling_strategy: CoverageStrategy = Field(default_factory=CoverageStrategy)


class JobService:
    def __init__(self,root):
        self.root=Path(root);self.queue=Queue();self.slots=BoundedSemaphore(5)
        self.events={};self.lock=Lock();self.stopping=Event()
        # Restart recovery never replays a partially completed job implicitly.
        for path in (self.root/'jobs').glob('*/status.json'):
            try:
                status=json.loads(path.read_text())
                if status.get('state') in ('queued','prepared','running'):
                    _write_json(path,dict(id=path.parent.name,state='interrupted',finished_at=_stamp(),message='Server restarted before completion. Submit a new job.'))
            except (OSError,ValueError):logger.warning('Unreadable job status: %s',path.parent.name)
        self.thread=Thread(target=self._loop,name='meosar-job-queue',daemon=True);self.thread.start()
    def submit(self,mission,libraries,tle):
        if self.stopping.is_set():_error('Server is stopping.',503)
        if not self.slots.acquire(blocking=False):_error('Job capacity reached (one running and four waiting). Try later.',429)
        try:
            job_id=prepare_job(self.root,mission,libraries,tle)
            _write_json(_job_path(self.root,job_id)/'status.json',dict(id=job_id,state='queued',created_at=_stamp()))
            with self.lock:self.events[job_id]=Event()
            self.queue.put(job_id);return job_id
        except Exception:self.slots.release();raise
    def _loop(self):
        while not self.stopping.is_set():
            try:job_id=self.queue.get(timeout=.5)
            except Empty:continue
            try:
                with self.lock:cancel=self.events[job_id]
                if cancel.is_set():
                    _write_json(_job_path(self.root,job_id)/'status.json',dict(id=job_id,state='cancelled',finished_at=_stamp()))
                else:run_job(self.root,job_id,cancel_event=cancel)
            except Exception:
                logger.exception('Worker failed for job %s',job_id)
                _write_json(_job_path(self.root,job_id)/'status.json',dict(id=job_id,state='failed',finished_at=_stamp(),message='Worker failed; check server logs.'))
            finally:
                with self.lock:self.events.pop(job_id,None)
                self.slots.release();self.queue.task_done()
    def shutdown(self):
        self.stopping.set()
        with self.lock:
            for event in self.events.values():event.set()
        self.thread.join(timeout=8)


def service(request):return request.app.state.jobs


def find_job(request,job_id):
    try:path=_job_path(service(request).root,job_id)
    except ValueError:_error('Job not found.',404)
    if not (path/'status.json').is_file():_error('Job not found.',404)
    return path


@router.get('/resources')
def resources():
    try:return {key:loader() for key,loader in LIBRARIES.items()}
    except (OSError,ValueError):_error('Library data could not be read.',503)


@router.post('/libraries/{kind}')
async def import_library(kind:str,request:Request):
    if kind not in LIBRARIES:_error('Unknown library.',404)
    data=validate_library(kind,await read_json(request))
    with library_lock:
        save_json(kind+'.json',data)
    return {'kind':kind,'records':len(data)}


@router.post('/tles')
async def import_tle(request:Request):
    data=await read_json(request,12*1024*1024)
    if not isinstance(data,dict) or set(data)-{'text','name'}:_error('Expected TLE text and optional name.')
    return store_tle(service(request).root, data.get('text'), data.get('name','Imported TLE'))


def store_tle(root, text, name, source='upload'):
    """Validate and content-address all TLE inputs through one storage boundary."""
    from sgp4.api import Satrec
    if isinstance(text,str):text=text.lstrip('\ufeff')
    if not isinstance(text,str) or not text.strip() or len(text.encode())>10*1024*1024:_error('TLE must be nonempty and at most 10 MiB.')
    if not _label(name):_error('Invalid TLE filename label.')
    lines=text.splitlines();count=0;identifiers=set()
    for index,line in enumerate(lines):
        if not line.startswith('1 '):continue
        next_index=index+1
        while next_index<len(lines) and not lines[next_index].strip():next_index+=1
        if next_index>=len(lines):_error('Missing second line of a TLE pair.')
        other=lines[next_index]
        if len(line)<63 or len(other)<63 or not other.startswith('2 ') or line[2:7]!=other[2:7]:_error('Mismatched or incomplete TLE pair.')
        try:
            satellite=Satrec.twoline2rv(line,other)
            if not math.isfinite(satellite.jdsatepoch) or not math.isfinite(satellite.no_kozai) or satellite.no_kozai<=0:raise ValueError()
        except (ValueError,TypeError,OverflowError):_error('TLE fields could not be parsed.')
        count+=1;identifiers.add(str(satellite.satnum))
    if not count or count>10000:_error('TLE must contain between 1 and 10,000 parsable pairs.')
    key=hashlib.sha256(text.encode()).hexdigest();folder=Path(root)/'tles'
    path=folder/(key+'.tle')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder,
                                         prefix='.tle-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        # Content-addressed identical uploads may replace only identical bytes;
        # the atomic rename keeps concurrent importers from seeing partial TLEs.
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    _write_json(folder/(key+'.json'),dict(id=key,name=name,records=count,satellites=len(identifiers),imported_at=_stamp(),source=source))
    return {'id':key,'records':count,'satellites':len(identifiers),'name':name}


@router.get('/tles')
def tles(request:Request):
    rows=[]
    for path in (service(request).root/'tles').glob('*.json'):
        try:rows.append(json.loads(path.read_text()))
        except (OSError,ValueError):continue
    return sorted(rows,key=lambda r:r.get('imported_at',''),reverse=True)


@router.post('/jobs',status_code=202)
async def submit_job(request:Request):
    data=await read_json(request)
    try:entry=MissionRequest.model_validate(data)
    except ValidationError as exc:_error('; '.join('.'.join(str(v) for v in e['loc'])+': '+e['msg'] for e in exc.errors()))
    return await queue_mission(request,entry)


async def queue_mission(request,entry,imported=None):
    if not _label(entry.mission_name):_error('Mission name must be one nonempty line.')
    if entry.event_type not in ('Landing','Launch','Testing'):_error('Choose a supported event type.')
    if entry.event_time.tzinfo is None:_error('Event time must include UTC or timezone offset.')
    if not 0<entry.hours_before+entry.hours_after<=2*(168+59/60):_error('Tracking window must be greater than zero and at most 168 h 59 min before and after the event.')
    with library_lock:
        libraries={kind:validate_library(kind,loader()) for kind,loader in LIBRARIES.items()}
    if entry.mission_location not in libraries['locations'] or entry.ground_station not in libraries['locations']:_error('Choose saved locations.')
    if any(v not in libraries['satellites'] for v in entry.satellites):_error('Selected satellite is not in the server library.')
    if any(v not in libraries['antennas'] or not libraries['antennas'][v]['operational'] for v in entry.antennas):_error('Choose operational antennas.')
    imported_schedule=None
    if imported is not None:
        from .schedule_import_api import normalize_imported
        imported_schedule=normalize_imported(imported,entry,libraries)
    if entry.tle_id == 'auto':
        from starlette.concurrency import run_in_threadpool
        from .mission_api import automatic_selection
        selected=await run_in_threadpool(automatic_selection,service(request).root,entry.satellites,entry.event_time)
        entry.tle_id=selected['id']
    if not re.fullmatch('[a-f0-9]{64}',entry.tle_id):_error('Choose an imported TLE.')
    path=service(request).root/'tles'/(entry.tle_id+'.tle')
    if not path.is_file():_error('TLE not found.',404)
    mission=entry.model_dump(exclude={'tle_id'})
    mission['satellites']={n:libraries['satellites'][n]['meosar_id'] for n in dict.fromkeys(entry.satellites)}
    mission['antennas']={name:libraries['antennas'][name] for name in dict.fromkeys(entry.antennas)}
    strategy=entry.scheduling_strategy.model_dump()
    strategy['geometry']=True
    if not strategy['enabled']:strategy['locations']=[]
    mission['scheduling_strategy']=strategy
    mission['tle_source_id']=entry.tle_id
    if imported_schedule is not None:mission['imported_schedule']=imported_schedule
    job_id=service(request).submit(mission,libraries,path.read_text(encoding='utf-8'))
    return {'id':job_id,'state':'queued'}


@router.get('/jobs')
def jobs(request:Request,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    rows=[]
    for path in sorted((service(request).root/'jobs').glob('*/status.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            row=json.loads(path.read_text());
            if row.get('hidden_from_history'):continue
            mission=json.loads((path.parent/'mission.json').read_text())
            row['mission_name']=mission.get('mission_name','');row['kind']='imported' if 'imported_schedule' in mission else 'generated';rows.append(row)
        except (OSError,ValueError):continue
    return rows[offset:offset+limit]


@router.get('/jobs/{job_id}')
def job_status(job_id:str,request:Request):
    path=find_job(request,job_id);status=json.loads((path/'status.json').read_text())
    if status.get('state')=='completed':
        result=json.loads((path/'result.json').read_text())
        status['kind']='imported' if result.get('import_source') else 'generated'
        status['import_notices']=(result.get('import_warnings',[])+result.get('import_validation_errors',[]))[:30]
        status['diagnostics']=result.get('schedule_diagnostics',{})
        status['selection_audit']=result.get('selection_audit',{})
        status['downloads']=sorted(p.name for p in [*(path/'graphs').glob('*.png'),*(path/'exports').glob('*'),path/'result.json'] if p.is_file() and p.name in DOWNLOADS)
    return status


@router.post('/jobs/{job_id}/cancel')
async def cancel_job(job_id:str,request:Request):
    await read_json(request)
    find_job(request,job_id)
    with service(request).lock:
        event=service(request).events.get(job_id)
        if event:event.set()
    return {'id':job_id,'cancellation_requested':event is not None}


@router.get('/jobs/{job_id}/files/{name}')
def job_file(job_id:str,name:str,request:Request,inline:bool=False):
    if name not in DOWNLOADS:_error('File not found.',404)
    path=find_job(request,job_id)
    if json.loads((path/'status.json').read_text()).get('state')!='completed':_error('Job is not complete.',409)
    folder='graphs' if name.endswith('.png') else 'exports' if name.startswith('schedule.') else ''
    target=path/folder/name
    if not target.is_file():_error('File not found.',404)
    return FileResponse(target,filename=None if inline and name.endswith('.png') else name,media_type='image/png' if name.endswith('.png') else 'application/json' if name.endswith('.json') else 'text/plain')


def library_revision(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


@router.get('/libraries/{kind}')
def library_snapshot(kind: str):
    if kind not in LIBRARIES:_error('Unknown library.',404)
    with library_lock:
        data=LIBRARIES[kind]()
    return {'records': data, 'revision': library_revision(data)}


@router.post('/libraries/{kind}/record')
async def change_record(kind: str, request: Request):
    if kind not in LIBRARIES:_error('Unknown library.',404)
    body=await read_json(request)
    if not isinstance(body,dict) or set(body)-{'revision','original','key','record','delete'}:
        _error('Invalid library update.')
    with library_lock:
        data=LIBRARIES[kind]()
        if body.get('revision')!=library_revision(data):
            _error('Library changed in another window. Reopen it before saving.',409)
        original=body.get('original')
        if original is not None and original not in data:_error('Record no longer exists.',409)
        if body.get('delete') is True:
            if original is None:_error('Choose a record to delete.')
            del data[original]
        else:
            key=body.get('key')
            if not _label(key):_error('Enter a valid name or NORAD ID.')
            if key!=original and key in data:_error('That name or ID already exists.',409)
            if original is not None:del data[original]
            data[key]=body.get('record')
            data=validate_library(kind,data)
        save_json(kind+'.json',data)
    return {'records':data,'revision':library_revision(data)}


@router.get('/tles/{tle_id}/epochs')
def tle_epochs(tle_id: str, request: Request, at: datetime | None = None):
    from sgp4.api import Satrec
    from datetime import timedelta
    if not re.fullmatch('[a-f0-9]{64}',tle_id):_error('TLE not found.',404)
    path=service(request).root/'tles'/(tle_id+'.tle')
    if not path.is_file():_error('TLE not found.',404)
    when=at or datetime.now(timezone.utc)
    if when.tzinfo is None:_error('Reference time must include a timezone.')
    lines=path.read_text().splitlines();best={}
    for index,line in enumerate(lines):
        if not line.startswith('1 '):continue
        second=index+1
        while second<len(lines) and not lines[second].strip():second+=1
        sat=Satrec.twoline2rv(line,lines[second])
        epoch=datetime(2000,1,1,12,tzinfo=timezone.utc)+timedelta(days=(sat.jdsatepoch-2451545.0)+sat.jdsatepochF)
        key=str(sat.satnum)
        age=(when-epoch).total_seconds()/86400
        if key not in best or abs(age)<abs(best[key]['age_days']):
            best[key]={'norad_id':key,'epoch':epoch.isoformat(),'age_days':age}
    return {'reference_time':when.isoformat(),'records':sorted(best.values(),key=lambda r:int(r['norad_id']))}


@router.get('/jobs/{job_id}/inputs')
def job_inputs(job_id: str, request: Request):
    path=find_job(request,job_id)
    mission=json.loads((path/'mission.json').read_text())
    mission['satellites']=list(mission['satellites'])
    mission['antennas']=list(mission['antennas'])
    mission['tle_id']=mission.pop('tle_source_id',None) or hashlib.sha256((path/'input.tle').read_bytes()).hexdigest()
    return mission


@router.get('/jobs/{job_id}/tle-summary')
def job_tle_summary(job_id: str, request: Request, max_age_days: int = Query(10, ge=1, le=3650)):
    """Report the frozen job records, rather than today's editable library."""
    from simulation.orbit_engine import OrbitEngine
    path=find_job(request,job_id)
    mission=json.loads((path/'mission.json').read_text())
    when=datetime.fromisoformat(mission['event_time'].replace('Z','+00:00'))
    engine=OrbitEngine(path);engine.load_tle_file(path/'input.tle')
    ages=[]
    for key in mission['satellites']:
        if str(key) in engine.tle_candidates:
            epoch=engine._select_record(str(key),when)['epoch_utc']
            ages.append((when-epoch).total_seconds()/86400)
    source=mission.get('tle_source_id','')
    metadata=service(request).root/'tles'/(source+'.json') if re.fullmatch('[a-f0-9]{64}',source) else None
    info=json.loads(metadata.read_text()) if metadata and metadata.exists() else {}
    return {'source':info.get('name') or info.get('filename') or source or 'Frozen job TLE records',
        'source_files':info.get('source_files',[]),'source_id':source,'reference_time':when.isoformat(),'available':len(ages),'requested':len(mission['satellites']),
        'average_age_days':sum(ages)/len(ages) if ages else None,'future_records':sum(a<0 for a in ages),'old_records':sum(a>=max_age_days for a in ages),'max_age_days':max_age_days}


@router.post('/jobs/clear')
async def clear_job_history(request: Request):
    data=await read_json(request)
    if not isinstance(data,dict) or set(data)-{'confirm','job_id'} or data.get('confirm') is not True:_error('Confirm clearing previous jobs.')
    if 'job_id' in data and not isinstance(data['job_id'],str):_error('Invalid job identifier.')
    selected=find_job(request,data['job_id']) if 'job_id' in data else None
    count=0
    with service(request).lock:
        for path in ([selected/'status.json'] if selected else (service(request).root/'jobs').glob('*/status.json')):
            row=json.loads(path.read_text())
            if selected and row.get('state') not in {'completed','failed','cancelled','interrupted'}:_error('A running or queued job cannot be cleared. Cancel it or wait for completion.',409)
            if row.get('state') not in {'completed','failed','cancelled','interrupted'} or row.get('hidden_from_history'):continue
            row['hidden_from_history']=True;_write_json(path,row);count+=1
    return {'cleared':count,'notice':'Finished jobs removed from history. Job files and saved schedule references are preserved.'}
