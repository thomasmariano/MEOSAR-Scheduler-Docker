"""Browser transport for the existing simulator engine and dashboard assets."""
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock, BoundedSemaphore
import base64
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from starlette.concurrency import run_in_threadpool
from simulation.dashboard_assets import load_dashboard_html
from simulation.orbit_engine import OrbitEngine, CoverageEventSearch
from .scheduling_api import find_job, read_json, _error, validate_library, _label
from .schedule_editing_api import load_context, state_for

router=APIRouter()
frame_slots=BoundedSemaphore(4)
engine_setup_lock=Lock()


def frozen_result(path, revision):
    context, original, mission=load_context(path)
    if revision=='original':return original, mission
    state=state_for(path)
    retained=path/'retained-revisions.json'
    kept=json.loads(retained.read_text()) if retained.exists() else []
    if revision not in state['history'] and revision not in kept:_error('Edited revision not found.',404)
    return json.loads((path/'edits'/revision/'result.json').read_text()), mission


def bootstrap(path, revision):
    result,mission=frozen_result(path,revision)
    locations=json.loads((path/'config/locations.json').read_text())
    metadata=json.loads((path/'config/satellites.json').read_text())
    assignments=[dict(a,antenna=name,satellite_id=str(a['norad_id']),
                      startMs=int(datetime.fromisoformat(a['start']).timestamp()*1000),
                      endMs=int(datetime.fromisoformat(a['end']).timestamp()*1000))
                 for name,rows in result['schedule'].items() for a in rows]
    def site(name,identifier):return dict(locations[name],name=name,id=identifier)
    source_id=mission.get('tle_source_id')
    source_label='Frozen job TLE snapshot'
    if source_id:
        metadata_path=path.parents[1]/'tles'/(source_id+'.json')
        if metadata_path.is_file():source_label=json.loads(metadata_path.read_text()).get('name',source_label)
    return dict(job_id=path.name,revision=revision,mission_name=mission['mission_name'],tle_source=source_label,
                station=site(mission['ground_station'],'station'),
                mission_site=site(mission['mission_location'],'mission'),
                locations=locations,metadata=metadata,
                schedule=dict(source=mission['mission_name']+' · '+revision,
                    assignments=assignments,satellite_ids=sorted({a['satellite_id'] for a in assignments}),
                    mission_info=dict(name=mission['mission_name'],type=mission['event_type'],event_time=mission['event_time']),
                    startMs=int(datetime.fromisoformat(result['tracking_start']).timestamp()*1000),
                    endMs=int(datetime.fromisoformat(result['tracking_end']).timestamp()*1000),warnings=[]))


@lru_cache(maxsize=4)
def _cached_engine(path_text):
    path=Path(path_text);engine=OrbitEngine(path)
    engine.load_tle_file(path/'input.tle')
    engine.satellites={key:max(records,key=lambda r:r['epoch_utc']) for key,records in engine.tle_candidates.items()}
    return engine,Lock(),{}


def engine_for(path_text):
    with engine_setup_lock:
        return _cached_engine(path_text)


@lru_cache(maxsize=1)
def dashboard_template():
    texture=Path(__file__).resolve().parents[1]/'assets/earth_texture.jpg'
    encoded=base64.b64encode(texture.read_bytes()).decode() if texture.is_file() else ''
    html=load_dashboard_html().replace('__EARTH_TEXTURE_BASE64__',encoded)
    html=html.replace('  for (const location of coverageLocations()) {', '  const locationLabels=[],seenLocations=new Set();\n  for (const location of coverageLocations()) {')
    html=html.replace('    if (p.depth <= 0) continue;\n    const summary = coverageSummary(location);', "    if (p.depth <= 0) continue;\n    const identity=location.name+'|'+Number(location.latitude).toFixed(4)+'|'+Number(location.longitude).toFixed(4);if(seenLocations.has(identity))continue;seenLocations.add(identity);\n    const summary = coverageSummary(location);")
    old="""    const labelX=Math.max(8,Math.min(p.x+13,W-textWidth-14));
    const labelY=Math.max(22,Math.min(p.y-10,H-22));"""
    new="""    const candidates=[];
    for(let offset=0;offset<20;offset++)for(const side of [1,-1])for(const direction of [-1,1]) {
      const x=Math.max(8,Math.min(side>0?p.x+15:p.x-textWidth-15,W-textWidth-14));
      const y=Math.max(22,Math.min(p.y-10+direction*offset*23,H-22));
      const box={x:x-5,y:y-13,w:textWidth+10,h:21};
      const overlap=locationLabels.reduce((sum,b)=>sum+Math.max(0,Math.min(box.x+box.w,b.x+b.w)-Math.max(box.x,b.x))*Math.max(0,Math.min(box.y+box.h,b.y+b.h)-Math.max(box.y,b.y)),0);
      candidates.push({x,y,box,cost:overlap*1000+Math.hypot(x-p.x,y-p.y)});
    }
    candidates.sort((a,b)=>a.cost-b.cost);const chosen=candidates[0];
    const labelX=chosen.x,labelY=chosen.y;locationLabels.push(chosen.box);
    ctx.beginPath();ctx.strokeStyle='rgba(220,235,255,.7)';ctx.lineWidth=1;ctx.moveTo(p.x,p.y);ctx.lineTo(Math.max(labelX,Math.min(p.x,labelX+textWidth)),labelY-4);ctx.stroke();"""
    return html.replace(old,new)


@router.get('/simulator/{job_id}',response_class=HTMLResponse)
def simulator_page(job_id:str,request:Request,revision:str='original'):
    path=find_job(request,job_id);data=bootstrap(path,revision)
    payload=json.dumps(data).replace('<','\\u003c')
    html=dashboard_template().replace('</body>',
        '<script>const simulatorConfig='+payload+';</script><script src="/simulator_bridge.js"></script><script src="/video_studio.js"></script><script src="/web_ui.js"></script></body>')
    return HTMLResponse(html,headers={'Cache-Control':'no-store'})


@router.get('/simulator_bridge.js')
def bridge_script():
    return FileResponse(Path(__file__).with_name('simulator_bridge.js'),media_type='text/javascript',headers={'Cache-Control':'no-cache'})


def request_context(path,data):
    if not isinstance(data,dict) or set(data)-{'time','revision','pins','paths','command'}:_error('Invalid simulation request.')
    revision=data.get('revision','original')
    result,mission=frozen_result(path,revision)
    try:
        when=datetime.fromisoformat(data['time'].replace('Z','+00:00'))
        if when.tzinfo is None:raise ValueError()
        when=when.astimezone(timezone.utc)
        if not datetime.fromisoformat(result['tracking_start'])<=when<=datetime.fromisoformat(result['tracking_end']):raise ValueError()
    except (KeyError,TypeError,ValueError,AttributeError):_error('Simulation time must be within the job window and include UTC.')
    pins=data.get('pins',[])
    if not isinstance(pins,list) or len(pins)>10:_error('At most 10 monitoring pins are supported.')
    checked=[]
    for index,pin in enumerate(pins):
        if not isinstance(pin,dict):_error('Invalid pin.')
        name=pin.get('name')
        if not _label(name):_error('Each pin needs a valid location name.')
        location=validate_library('locations',{name:pin})[name]
        checked.append(dict(location,name=name,id='pin-'+str(index)))
    stored=json.loads((path/'config/locations.json').read_text())
    places=[dict(stored[mission['ground_station']],name=mission['ground_station'],id='station'),
            dict(stored[mission['mission_location']],name=mission['mission_location'],id='mission'),*checked]
    return result,mission,when,places


def calculate_frame(path,data):
    if not frame_slots.acquire(blocking=False):_error('Simulation workers are busy. Try again.',429)
    engine=None;locked=False
    try:
        result,mission,when,places=request_context(path,data)
        engine,lock,path_cache=engine_for(str(path))
        locked=lock.acquire(blocking=False)
        if not locked:_error('This job is processing another simulation request.',429)
        library=json.loads((path/'config/satellites.json').read_text())
        scheduled={str(a['norad_id']) for rows in result['schedule'].values() for a in rows}
        ids=sorted((set(library)&set(engine.satellites))|scheduled)
        if len(ids)>200:_error('Simulator is limited to 200 configured satellites per job.')
        rows=[]
        for key in ids:
            try:
                row=engine.propagate(key,when)
                row['visibility']=engine.visibility_from_location(row,places[0])
                row['location_visibility']={p['id']:engine.visibility_from_location(row,p) for p in places}
                xyz=row['ecef_km'];row['ecef_km']=[xyz['x'],xyz['y'],xyz['z']]
                row.pop('tle_line1',None);row.pop('tle_line2',None)
                row['source_file']='Job TLE snapshot'
            except (KeyError,ValueError,RuntimeError,OverflowError):
                row={'norad_id':key,'error':'Propagation or visibility unavailable for this satellite.'}
            row.update(satellite_id=key,scheduled=key in scheduled);rows.append(row)
        response={'time':when.isoformat(),'results':rows}
        if data.get('paths') is True:
            cache_key=(int(when.timestamp()//300),tuple((key,engine._select_record(key,when)['epoch_utc']) for key in ids if key in engine.satellites))
            if cache_key not in path_cache:
                paths=[]
                for key in ids:
                    if key not in engine.satellites:continue
                    try:paths.append(engine.propagate_orbit_track(key,when,samples=72))
                    except (KeyError,ValueError,RuntimeError,OverflowError):continue
                path_cache.clear();path_cache[cache_key]=paths
            response['paths']=path_cache[cache_key]
        return response
    finally:
        if locked:lock.release()
        frame_slots.release()


@router.post('/api/jobs/{job_id}/simulation/frame')
async def simulation_frame(job_id:str,request:Request):
    data=await read_json(request,32*1024)
    return await run_in_threadpool(calculate_frame,find_job(request,job_id),data)


def search_event(path,data):
    result,mission,when,places=request_context(path,data)
    command=data.get('command')
    if not isinstance(command,dict) or type(command.get('id')) is not int:_error('Invalid navigation command.')
    if command.get('direction') not in (-1,1) or command.get('kind') not in ('any','loss','recovery'):_error('Invalid navigation direction or kind.')
    location_id=command.get('locationId','all')
    places=[p for p in places if location_id=='all' or p['id']==location_id]
    if not places:_error('Choose a monitored location.')
    if not frame_slots.acquire(blocking=False):_error('Simulation workers are busy.',429)
    engine,lock,_=engine_for(str(path))
    if not lock.acquire(blocking=False):
        frame_slots.release()
        _error('Simulator is busy; try the search again.',429)
    try:
        start=int(datetime.fromisoformat(result['tracking_start']).timestamp()*1000)
        end=int(datetime.fromisoformat(result['tracking_end']).timestamp()*1000)
        assignments=[dict(satellite_id=str(a['norad_id']),startMs=int(datetime.fromisoformat(a['start']).timestamp()*1000),
                         endMs=int(datetime.fromisoformat(a['end']).timestamp()*1000)) for rows in result['schedule'].values() for a in rows]
        search=CoverageEventSearch(engine,assignments,places,start,end,int(when.timestamp()*1000),
                                  direction=command['direction'],kind=command['kind'])
        deadline=time.monotonic()+20
        for event in search.run():
            if event['status']!='progress':return dict(event,id=command['id'])
            if time.monotonic()>deadline:
                return dict(status='limited',id=command['id'],message='Search reached its 20-second limit. Move closer to the interval of interest and retry.')
        return dict(status='none',id=command['id'])
    finally:
        lock.release()
        frame_slots.release()


@router.post('/api/jobs/{job_id}/simulation/event')
async def simulation_event(job_id:str,request:Request):
    data=await read_json(request,32*1024)
    return await run_in_threadpool(search_event,find_job(request,job_id),data)
