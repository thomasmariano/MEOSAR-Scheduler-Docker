"""Bounded streaming PNG-to-FFmpeg exports for a job's frozen simulator input."""
from pathlib import Path
from threading import Lock, Event, Thread, BoundedSemaphore
from uuid import UUID, uuid4
import json
import os
import select
import shutil
import struct
import subprocess
import time

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from .scheduling_api import read_json, find_job, _error
from .simulator_api import frozen_result
from .job_runner import _write_json, _stamp

router=APIRouter(prefix='/api')
MAX_PNG=12*1024*1024


def video_limits():
    definitions={
        'max_seconds':('MEOSAR_VIDEO_MAX_SECONDS',600,1,86400),
        'max_frames':('MEOSAR_VIDEO_MAX_FRAMES',18000,2,2592000),
        'session_seconds':('MEOSAR_VIDEO_SESSION_SECONDS',7200,60,86400),
    }
    limits={}
    for key,(name,default,minimum,maximum) in definitions.items():
        try:value=int(os.environ.get(name,str(default)))
        except ValueError:raise RuntimeError(name+' must be an integer.')
        if not minimum<=value<=maximum:raise RuntimeError(name+f' must be between {minimum} and {maximum}.')
        limits[key]=value
    return limits


class VideoService:
    def __init__(self,root):
        self.limits=video_limits()
        self.root=Path(root);self.slot=BoundedSemaphore(1);self.active={};self.lock=Lock();self.stop=Event()
        for path in (self.root/'jobs').glob('*/videos/*/status.json'):
            try:
                state=json.loads(path.read_text())
                if state.get('state') in ('receiving','encoding'):
                    state.update(state='interrupted',message='Server restarted. Export again.',finished_at=_stamp())
                    _write_json(path,state)
                    for file in path.parent.glob('video.*.part'):file.unlink(missing_ok=True)
            except (OSError,ValueError):pass
        self.thread=Thread(target=self._reaper,daemon=True,name='video-idle-cleanup');self.thread.start()

    def _reaper(self):
        while not self.stop.wait(10):
            with self.lock:rows=list(self.active.values())
            for row in rows:
                if time.monotonic()-row['touched']>180 or time.monotonic()-row['started']>self.limits['session_seconds']:
                    self.cancel(row,'Export timed out after inactivity or its configured session limit.')

    def cancel(self,row,message='Export cancelled.'):
        row['cancelled'].set()
        process=row['process']
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        with row['io']:
            if row['released']:return
            if process.stdin and not process.stdin.closed:process.stdin.close()
            row['state'].update(state='cancelled',message=message,finished_at=_stamp())
            _write_json(row['folder']/'status.json',row['state'])
            row['output'].unlink(missing_ok=True)
            self.release(row)

    def release(self,row):
        if row['released']:return
        row['released']=True
        row['log'].close()
        with self.lock:self.active.pop(row['id'],None)
        self.slot.release()

    def close(self):
        self.stop.set()
        with self.lock:rows=list(self.active.values())
        for row in rows:self.cancel(row,'Server stopped during export.')
        self.thread.join(timeout=2)


def video_service(request):return request.app.state.videos


def settings_for(path,data):
    required={'revision','first','last','fps','frames','width','height','format','kbps'}
    if not isinstance(data,dict) or set(data)!=required:_error('Invalid video settings.')
    if not isinstance(data['revision'],str):_error('Choose a schedule revision.')
    result,_=frozen_result(path,data['revision'])
    from datetime import datetime
    start=round(datetime.fromisoformat(result['tracking_start']).timestamp()*1000)
    end=round(datetime.fromisoformat(result['tracking_end']).timestamp()*1000)
    for key in ('first','last','fps','frames','width','height','kbps'):
        if type(data[key]) is not int:_error('Video settings must use integer sizes, counts and timestamps.')
    if not start<=data['first']<data['last']<=end:_error('Video interval must be within the mission window.')
    limits=video_limits()
    if data['fps'] not in (10,12,15,24,30) or not 2<=data['frames']<=limits['max_frames'] or data['frames']/data['fps']>limits['max_seconds']:
        _error(f"Use 10/12/15/24/30 FPS, at most {limits['max_frames']} frames and {limits['max_seconds']} seconds of output.")
    w,h=data['width'],data['height']
    if not 320<=w<=7000 or not 180<=h<=3500 or w%2 or h%2 or w*h>20_000_000:_error('Unsupported output dimensions.')
    if data['format'] not in ('mp4','webm') or not 200<=data['kbps']<=30000:_error('Unsupported format or bitrate.')
    return dict(data)


def start_video(path,data,manager):
    settings=settings_for(path,data)
    executable=shutil.which('ffmpeg')
    if not executable:_error('FFmpeg is missing on the server. Rebuild the updated Docker image.',503)
    if not manager.slot.acquire(blocking=False):_error('Another video export is active. Try again when it finishes.',429)
    folder=None;log=None;process=None
    try:
        identifier=str(uuid4());folder=path/'videos'/identifier;folder.mkdir(parents=True)
        fmt=settings['format'];output=folder/('video.'+fmt+'.part')
        command=[executable,'-hide_banner','-loglevel','error','-y','-xerror','-f','image2pipe','-framerate',str(settings['fps']),'-vcodec','png','-i','pipe:0','-an']
        if fmt=='mp4':command+=['-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-movflags','+faststart']
        else:command+=['-c:v','libvpx-vp9','-deadline','good','-cpu-used','4','-pix_fmt','yuv420p']
        command+=['-threads','2','-b:v',str(settings['kbps'])+'k','-maxrate',str(settings['kbps'])+'k','-bufsize',str(settings['kbps']*2)+'k','-f',fmt,str(output)]
        log=(folder/'encoder.log').open('wb')
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=log)
        os.set_blocking(process.stdin.fileno(),False)
        state=dict(id=identifier,job_id=path.name,state='receiving',received=0,frames=settings['frames'],created_at=_stamp(),settings=settings)
        _write_json(folder/'status.json',state)
        row=dict(id=identifier,folder=folder,output=output,process=process,log=log,state=state,
                 settings=settings,io=Lock(),cancelled=Event(),released=False,started=time.monotonic(),touched=time.monotonic(),last_hash=None)
        with manager.lock:manager.active[identifier]=row
        return dict(state)
    except Exception:
        if process is not None and process.poll() is None:process.kill();process.wait()
        if log is not None:log.close()
        manager.slot.release()
        if folder is not None:shutil.rmtree(folder,ignore_errors=True)
        raise


def canonical(identifier):
    try:
        if str(UUID(identifier))!=identifier:raise ValueError()
    except (ValueError,AttributeError):_error('Video export not found.',404)


def active_row(request,path,identifier):
    canonical(identifier)
    with video_service(request).lock:row=video_service(request).active.get(identifier)
    if not row or row['folder'].parent.parent!=path:_error('Active export not found.',404)
    return row


def write_frame(row,index,png,stamp):
    import hashlib
    with row['io']:
        if row['cancelled'].is_set() or row['released']:_error('Export is no longer active.',409)
        expected=row['state']['received'];settings=row['settings'];digest=hashlib.sha256(png).hexdigest()
        if index==expected-1 and digest==row['last_hash']:return dict(row['state'])
        if index!=expected or index>=settings['frames']:_error('Unexpected frame sequence.',409)
        expected_time=settings['first']+(settings['last']-settings['first'])*index/(settings['frames']-1)
        if abs(stamp-expected_time)>2:_error('Frame timestamp does not match the export timeline.')
        if len(png)<24 or png[:8]!=b'\x89PNG\r\n\x1a\n' or png[12:16]!=b'IHDR':_error('Expected PNG frame.')
        width,height=struct.unpack('>II',png[16:24])
        if (width,height)!=(settings['width'],settings['height']):_error('Frame dimensions changed during export.')
        process=row['process'];offset=0;deadline=time.monotonic()+30
        try:
            while offset<len(png):
                if row['cancelled'].is_set() or process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('Encoder stopped or timed out')
                _,ready,_=select.select([], [process.stdin.fileno()], [], .25)
                if ready:
                    try:offset+=os.write(process.stdin.fileno(),png[offset:offset+65536])
                    except BlockingIOError:continue
        except (OSError,RuntimeError):
            _error('Encoder stopped while receiving frames. Cancel and export again.',500)
        row['state']['received']+=1;row['last_hash']=digest;row['touched']=time.monotonic()
        _write_json(row['folder']/'status.json',row['state'])
        return dict(row['state'])


def finish_video(row,manager):
    with row['io']:
        if row['released'] or row['cancelled'].is_set():_error('Export is no longer active.',409)
        if row['state']['received']!=row['settings']['frames']:_error('Export has missing frames.',409)
        row['state']['state']='encoding';_write_json(row['folder']/'status.json',row['state'])
        row['touched']=time.monotonic()
        process=row['process'];process.stdin.close()
        try:
            code=process.wait(timeout=120)
            if code or row['cancelled'].is_set() or not row['output'].is_file():raise RuntimeError()
            final=row['folder']/('video.'+row['settings']['format']);row['output'].replace(final)
            row['state'].update(state='completed',finished_at=_stamp(),bytes=final.stat().st_size,filename=final.name)
        except (subprocess.TimeoutExpired,RuntimeError):
            if process.poll() is None:process.kill();process.wait()
            row['output'].unlink(missing_ok=True)
            row['state'].update(state='cancelled' if row['cancelled'].is_set() else 'failed',finished_at=_stamp(),message='Video encoding did not complete.')
        _write_json(row['folder']/'status.json',row['state']);manager.release(row)
        return dict(row['state'])


@router.get('/videos/capabilities')
def capabilities():
    return dict(available=shutil.which('ffmpeg') is not None,formats=['mp4','webm'],fps=[10,12,15,24,30],**video_limits())


@router.post('/jobs/{job_id}/videos')
async def create_video(job_id:str,request:Request):
    data=await read_json(request,8192)
    return await run_in_threadpool(start_video,find_job(request,job_id),data,video_service(request))


@router.post('/jobs/{job_id}/videos/{identifier}/frames/{index}')
async def upload_frame(job_id:str,identifier:str,index:int,request:Request):
    if request.headers.get('x-meosar-request')!='1':_error('Browser client header required.',403)
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):_error('Cross-origin writes are not permitted.',403)
    if request.headers.get('content-type')!='image/png':_error('Send image/png.',415)
    try:stamp=int(request.headers['x-simulation-time-ms'])
    except (KeyError,ValueError):_error('Frame UTC timestamp required.')
    row=active_row(request,find_job(request,job_id),identifier);raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>MAX_PNG:_error('PNG frame exceeds 12 MiB.',413)
    return await run_in_threadpool(write_frame,row,index,bytes(raw),stamp)


@router.post('/jobs/{job_id}/videos/{identifier}/finish')
async def complete_video(job_id:str,identifier:str,request:Request):
    await read_json(request)
    row=active_row(request,find_job(request,job_id),identifier)
    return await run_in_threadpool(finish_video,row,video_service(request))


@router.post('/jobs/{job_id}/videos/{identifier}/cancel')
async def cancel_video(job_id:str,identifier:str,request:Request):
    await read_json(request);path=find_job(request,job_id);canonical(identifier)
    with video_service(request).lock:row=video_service(request).active.get(identifier)
    if row and row['folder'].parent.parent==path:
        await run_in_threadpool(video_service(request).cancel,row)
    return {'cancelled':True}


@router.get('/jobs/{job_id}/videos')
def videos(job_id:str,request:Request):
    path=find_job(request,job_id);rows=[]
    for file in (path/'videos').glob('*/status.json'):
        try:rows.append(json.loads(file.read_text()))
        except (OSError,ValueError):continue
    return sorted(rows,key=lambda r:r.get('created_at',''),reverse=True)


@router.get('/jobs/{job_id}/videos/{identifier}/download')
def download(job_id:str,identifier:str,request:Request):
    path=find_job(request,job_id);canonical(identifier);folder=path/'videos'/identifier
    if not (folder/'status.json').is_file():_error('Video not found.',404)
    state=json.loads((folder/'status.json').read_text())
    if state.get('state')!='completed':_error('Video is not complete.',409)
    name='video.'+state['settings']['format']
    return FileResponse(folder/name,filename='MEOSAR-'+job_id[:8]+'-'+name,media_type='video/mp4' if name.endswith('mp4') else 'video/webm')
