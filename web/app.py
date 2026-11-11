"""Local browser scheduler, persistent libraries and isolated job execution."""
from contextlib import asynccontextmanager
from pathlib import Path
import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from config.config_manager import load_antennas, load_locations, load_satellites
from paths import get_config_directory, CONFIG_DIRECTORY
from version import APP_NAME, APP_VERSION
from .scheduling_api import router, JobService
from .tle_sources_api import router as tle_sources_router
from .schedule_editing_api import router as editing_router
from .mission_api import router as mission_router
from .simulator_api import router as simulator_router
from .video_api import router as video_router, VideoService
from .schedule_import_api import router as import_router
from .simulator_workflows import router as simulator_workflows_router
from .saved_missions_api import router as saved_missions_router

CONFIG_FILES = ('antennas.json', 'locations.json', 'satellites.json')


def seed_libraries(config, defaults):
    """Initialize missing libraries and migrate legacy empty placeholders once.

    A marker distinguishes old empty containers from intentionally emptied
    libraries. Changed/nonempty libraries are never replaced on deployment.
    """
    marker = config/'.defaults-v1.json'
    initial = not marker.exists()
    seeded = []
    for filename in CONFIG_FILES:
        target = config/filename
        exists = target.exists()
        legacy_empty = initial and exists and json.loads(target.read_text()) == {}
        if not exists or legacy_empty:
            source = defaults/filename
            data = json.loads(source.read_text(encoding='utf-8-sig'))
            if not isinstance(data, dict):
                raise ValueError('Bundled library must be a JSON object: '+filename)
            from .job_runner import _write_json
            _write_json(target, data)
            seeded.append(filename)
    if initial:
        from .job_runner import _write_json
        _write_json(marker, {'version': 1, 'seeded': seeded})


@asynccontextmanager
async def lifespan(app):
    # Container-managed state stays outside image resources and source files.
    value = os.environ.get('MEOSAR_DATA_DIR')
    if not value or not Path(value).is_absolute():
        raise RuntimeError('Set MEOSAR_DATA_DIR to an absolute writable data directory.')
    root = Path(value)
    config = get_config_directory()
    for directory in (root, config, root/'tles', root/'jobs', root/'exports'):
        directory.mkdir(parents=True, exist_ok=True)
    seed_libraries(config, CONFIG_DIRECTORY)
    app.state.jobs = JobService(root)
    app.state.videos = VideoService(root)
    app.state.ready = True
    try:
        yield
    finally:
        app.state.ready = False
        app.state.jobs.shutdown()
        app.state.videos.close()


app = FastAPI(title=APP_NAME+' Web', version=APP_VERSION, lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


@app.get('/healthz')
def health():
    if not getattr(app.state, 'ready', False):
        raise HTTPException(503, 'Starting')
    return {'status': 'ok', 'service': 'meosar-web', 'stage': 'browser-scheduler'}


@app.get('/api/status')
def status():
    try:
        antennas, locations, satellites = load_antennas(), load_locations(), load_satellites()
        if not all(isinstance(records, dict) for records in (antennas, locations, satellites)):
            raise ValueError('Library files must contain JSON objects.')
        if not all(isinstance(record, dict) for records in (antennas, satellites) for record in records.values()):
            raise ValueError('Satellite and antenna records must contain objects.')
    except (OSError, ValueError, TypeError):
        raise HTTPException(503, 'Library configuration could not be read. Check the server configuration.')
    return {
        'application': APP_NAME, 'version': APP_VERSION,
        'web_stage': 'Browser scheduler — local development',
        'libraries': {'locations': len(locations), 'satellites': len(satellites),
                      'enabled_satellites': sum(bool(s.get('enabled')) for s in satellites.values()),
                      'antennas': len(antennas),
                      'operational_antennas': sum(bool(a.get('operational')) for a in antennas.values())},
        'storage': 'Persistent container volume; independent of desktop libraries',
    }


@app.get('/')
def index():
    return FileResponse(Path(__file__).with_name('index.html'), headers={'Cache-Control':'no-cache'})

app.include_router(router)
app.include_router(tle_sources_router)
app.include_router(editing_router)
app.include_router(mission_router)
app.include_router(simulator_router)
app.include_router(video_router)
app.include_router(import_router)
app.include_router(simulator_workflows_router)
app.include_router(saved_missions_router)


@app.get('/workspace.js')
def workspace_script():
    return FileResponse(Path(__file__).with_name('workspace.js'), media_type='text/javascript', headers={'Cache-Control':'no-cache'})


@app.get('/parity.js')
def parity_script():
    return FileResponse(Path(__file__).with_name('parity.js'), media_type='text/javascript', headers={'Cache-Control':'no-cache'})


@app.get('/video_studio.js')
def video_studio_script():
    return FileResponse(Path(__file__).with_name('video_studio.js'), media_type='text/javascript', headers={'Cache-Control':'no-cache'})


@app.get('/schedule_draft_editor.js')
def draft_editor_script():
    return FileResponse(Path(__file__).with_name('schedule_draft_editor.js'),media_type='text/javascript',headers={'Cache-Control':'no-cache'})


@app.get('/web_ui.js')
def web_ui_script():
    return FileResponse(Path(__file__).with_name('web_ui.js'),media_type='text/javascript',headers={'Cache-Control':'no-cache'})
