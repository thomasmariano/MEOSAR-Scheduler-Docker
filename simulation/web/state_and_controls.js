
"use strict";

const $ = id => document.getElementById(id);
let schedule = null;
let orbitResults = [];
let orbitById = new Map();
let orbitPaths = [];
let showOrbitPaths = false;
let showGroundTracks = true;
let showCoverage = true;
let satelliteFilter = "scheduled";
let identifierMode = "meosar";
let satelliteSort = "label";
let sortDescending = false;
let satelliteMetadata = {};
let pointerDownX = 0, pointerDownY = 0;
let pointerSatelliteId = null;
let activeCoverageOnly = true;
let pinnedLocations = [];
const satelliteOptions = new Map();
let satelliteHits = [];
let layerTableKey = "";
let dataTimeMs = null;
let lastDynamicRefresh = 0;
let lastTrackingSignature = "";
let pendingNavigationCommand = null;
let activeNavigationId = null;
let navigationSequence = 0;
let navigationLocationsKey = "";

function setLayerVisibility() {
  satelliteFilter = $("satelliteFilter").value;
  activeCoverageOnly = $("activeCoverageOnly").checked;
  showOrbitPaths = $("showOrbits").checked;
  showGroundTracks = $("showGroundTracks").checked;
  showCoverage = $("showCoverage").checked;
  // Refresh counts as well as the globe when the filter changes.
  setOrbitData(orbitResults);
}

function setOrbitPaths(paths) {
  orbitPaths = Array.isArray(paths) ? paths : [];
  drawGlobe();
}
let selectedId = null;
let simTimeMs = Date.now();
let playing = false;
let speed = 60;
let lastFrame = 0;
let lastOrbitUpdate = 0;
let lastOrbitError = "";
let diagnostics = [];
let station = null;
let landingSite = null;
let canvas = null;
let ctx = null;

// Initial camera center: NASA Goddard Space Flight Center, Greenbelt.
// In this projection, yaw is negative longitude and pitch is latitude.
const GODDARD_LATITUDE = 38.9955;
const GODDARD_LONGITUDE = -76.8483;
let globeYaw = -GODDARD_LONGITUDE * Math.PI / 180;
let globePitch = GODDARD_LATITUDE * Math.PI / 180;
let globeZoom = 1.0;
// Orbital distances are compressed consistently for this dashboard view.
// Preserve the Earth-fixed direction while fitting MEO trajectories on screen.
const DISPLAY_ALTITUDE_FACTOR = 0.15;
function satelliteDisplayVector(ecef) {
  if (!Array.isArray(ecef) || ecef.length < 3 ||
      !ecef.slice(0, 3).every(Number.isFinite)) return null;
  const [x, y, z] = ecef;
  const norm = Math.hypot(x, y, z);
  if (norm < 1) return null;
  const scale = 1 + Math.max(0, norm / 6371 - 1) * DISPLAY_ALTITUDE_FACTOR;
  return [x / norm * scale, z / norm * scale, y / norm * scale];
}
function satelliteId(r) { return String(r?.satellite_id ?? r?.norad_id ?? ""); }
function metadataFor(id) { return satelliteMetadata[String(id)] || {}; }
function satelliteLabel(id) {
  id = String(id);
  const meosar = metadataFor(id).meosar_id;
  return identifierMode === "meosar" && meosar ? String(meosar) : id;
}
function labelDescription(id) {
  const meta = metadataFor(id);
  return `NORAD ${id} · MEOSAR ${meta.meosar_id || 'unknown'} · Band ${meta.band || 'unknown'}`;
}
function setSatelliteMetadata(data) {
  satelliteMetadata = data && typeof data === "object" ? data : {};
  layerTableKey = "";
  renderSchedule();
  refreshDashboard();
}
function setIdentifierMode(mode) {
  identifierMode = mode === "meosar" ? "meosar" : "norad";
  layerTableKey = "";
  renderSchedule();
  refreshDashboard();
}
function setSatelliteSort(value) {
  satelliteSort = ["label", "norad", "meosar", "state", "band"].includes(value) ? value : "label";
  layerTableKey = "";
  renderSatelliteLayers();
}
function toggleSortDirection() {
  sortDescending = !sortDescending;
  $("sortDirection").textContent = sortDescending ? "↓ DESC" : "↑ ASC";
  layerTableKey = "";
  renderSatelliteLayers();
}
function sortedSatelliteRecords(records) {
  const priority = r => {
    const state = trackingState(satelliteId(r));
    return state.active ? (satelliteState(r).warning ? 0 : 1)
      : state.past ? 2 : r.visibility?.visible ? 3 : 4;
  };
  const value = r => {
    const id = satelliteId(r), meta = metadataFor(id);
    if (satelliteSort === "state") return priority(r);
    if (satelliteSort === "band") return meta.band || null;
    if (satelliteSort === "meosar") return meta.meosar_id || null;
    return satelliteSort === "norad" ? id : satelliteLabel(id);
  };
  return [...records].sort((a,b) => {
    const va=value(a), vb=value(b);
    if (va == null || vb == null) return va == null && vb == null
      ? satelliteId(a).localeCompare(satelliteId(b), undefined, {numeric:true}) : va == null ? 1 : -1;
    const comparison = String(va).localeCompare(String(vb), undefined, {numeric:true, sensitivity:"base"});
    return (sortDescending ? -comparison : comparison) || satelliteId(a).localeCompare(satelliteId(b), undefined, {numeric:true});
  });
}
function findSatelliteHit(x,y) {
  return satelliteHits.map(p => ({...p, distance:Math.hypot(p.x-x,p.y-y)}))
    .filter(p => p.distance < 15 || (x >= p.x+5 && x <= p.x+8+p.labelWidth && y >= p.y-19 && y <= p.y+1))
    .sort((a,b) => a.distance-b.distance)[0] || null;
}

function optionsFor(id) {
  id = String(id);
  if (!satelliteOptions.has(id)) satelliteOptions.set(id, {enabled:true, orbit:true, ground:true, coverage:true});
  return satelliteOptions.get(id);
}
function trackingState(id, t=simTimeMs) {
  const rows = schedule?.assignments.filter(a => String(a.satellite_id) === String(id)) || [];
  return {
    scheduled: rows.length > 0,
    active: rows.some(a => assignmentActive(a, t)),
    past: rows.some(a => Number.isFinite(a.endMs) && a.endMs <= t)
  };
}
function satelliteState(r) {
  const tracking = trackingState(satelliteId(r));
  const visible = r?.visibility?.visible === true && !r?.error;
  if (tracking.active) return visible
    ? {color:"#52f0b0", label:"TRACKED", warning:false}
    : {color:"#ff647c", label:r?.visibility ? "TRACKED / NOT VISIBLE" : "TRACKED / VISIBILITY UNKNOWN", warning:true};
  if (tracking.past) return {color:"#ffbd69", label:"PAST TRACKED", warning:false};
  if (visible) return {color:"#5599ff", label:"VISIBLE / NOT TRACKED", warning:false};
  return {color:"#ff647c", label:r?.visibility ? "NOT VISIBLE" : "VISIBILITY UNKNOWN", warning:false};
}
function satelliteColor(satellite) {
  if(videoExportSnapshot && satellite) {
    const id=String(satellite.satellite_id??satellite.norad_id);
    const state=trackingState(id,dataTimeMs??simTimeMs);
    if(state.active) return satellite.visibility?.visible===true?'#52f0b0':'#ff6577';
    if(state.past) return '#ffad5b';
    if((schedule?.assignments||[]).some(a=>String(a.satellite_id)===id && a.startMs>(dataTimeMs??simTimeMs))) return '#59aaff';
    return '#91a4b8';
  }
  return satelliteState(satellite).color;
}
function hexColor(color) { return [1,3,5].map(index => parseInt(color.slice(index,index+2),16)); }
function passesSatelliteFilter(r) {
  if (!r) return false;
  const state = trackingState(satelliteId(r));
  return satelliteFilter === "all" || (satelliteFilter === "active" ? state.active : state.scheduled);
}
function layerVisible(r, layer) {
  if (!passesSatelliteFilter(r)) return false;
  const options = optionsFor(satelliteId(r));
  return options.enabled && (layer === "marker" || options[layer]);
}
function setSatelliteOption(id, layer, checked) {
  if (!["enabled", "orbit", "ground", "coverage"].includes(layer)) return;
  optionsFor(id)[layer] = !!checked;
  refreshDashboard();
}
function setPinnedLocations(locations) {
  if (activeNavigationId !== null) cancelCoverageNavigation('Monitoring locations changed; run the search again.');
  pinnedLocations = Array.isArray(locations) ? locations : [];
  refreshDashboard();
}
function coverageLocations() {
  const locations = [];
  if (station) locations.push({...station, id:"station", role:"Ground station"});
  if (landingSite) locations.push({...landingSite, id:"mission", role:"Mission site"});
  return locations.concat(pinnedLocations.map(p => ({...p, role:p.saved ? "Saved pin" : "Temporary pin"})));
}
function coverageSummary(location) {
  let count = 0, missing = 0, total = 0;
  for (const r of orbitResults) {
    // Counts follow the last propagated timestamp, independently of display filters.
    if (!trackingState(satelliteId(r), dataTimeMs ?? simTimeMs).active) continue;
    total++;
    const visibility = r.location_visibility?.[location.id];
    if (r.error || !visibility) { missing++; continue; }
    if (visibility.visible) count++;
  }
  // An assigned satellite without a TLE must not silently disappear from the totals.
  for (const id of schedule?.satellite_ids || []) {
    if (trackingState(id, dataTimeMs ?? simTimeMs).active && !orbitById.has(String(id))) { total++; missing++; }
  }
  const ready = dataTimeMs !== null;
  return {count, missing, total, ready, color: ready && count >= 3 ? "#52f0b0" : "#ffd166"};
}
function renderLocationCoverage() {
  $("coverageTime").textContent = dataTimeMs === null ? "Waiting for positions" : fmtTime(dataTimeMs);
  const locations = coverageLocations();
  $("locationCoverage").innerHTML = locations.length ? locations.map(location => {
    const summary = coverageSummary(location);
    const label = summary.ready ? `${summary.count} / ${summary.total} tracked` : "WAITING";
    return `<div class="coverage-row" style="border-left:3px solid ${summary.color}">
      <strong style="color:${summary.color}">${label}</strong>${escapeHtml(location.name)}
      <div class="panel-note">${escapeHtml(location.role)} · ${Number(location.latitude).toFixed(3)}°, ${Number(location.longitude).toFixed(3)}°${summary.missing ? ` · ${summary.missing} unknown` : ""}</div>
    </div>`;
  }).join("") : '<div class="coverage-row">Use PIN LOCATIONS to add a monitoring location.</div>';
}
function renderSatelliteLayers() {
  const ids = [...new Set([...orbitById.keys(), ...(schedule?.satellite_ids || []).map(String)])].sort();
  const records = ids.map(id => orbitById.get(id) || {satellite_id:id});
  const rows = sortedSatelliteRecords(records.filter(passesSatelliteFilter));
  const key = JSON.stringify([identifierMode, satelliteSort, sortDescending, rows.map(r => [satelliteId(r), satelliteLabel(satelliteId(r)), satelliteState(r).label, optionsFor(satelliteId(r)), satelliteId(r) === selectedId])]);
  if (key === layerTableKey) return;
  layerTableKey = key;
  $("satelliteLayers").innerHTML = rows.map(r => {
    const id = satelliteId(r), state = satelliteState(r), options = optionsFor(id);
    // IDs are data attributes; delegated listeners avoid inline JavaScript quoting.
    return `<tr class="${id===selectedId ? 'selected' : ''}"><td><button class="satellite-name" data-select="${escapeHtml(id)}" title="${escapeHtml(labelDescription(id) + ' · ' + state.label)}" style="color:${state.color}">● ${escapeHtml(satelliteLabel(id))}</button></td>${["enabled","orbit","ground","coverage"].map(layer => `<td><input type="checkbox" data-satellite="${escapeHtml(id)}" data-layer="${layer}" ${options[layer] ? "checked" : ""} aria-label="${layer} for ${escapeHtml(id)}"></td>`).join("")}</tr>`;
  }).join("");
}
function comparisonRecords() {
  if (!schedule || dataTimeMs === null) return [];
  return (schedule.satellite_ids || []).map(String).filter(id => trackingState(id, dataTimeMs).active).map(id => {
    const r=orbitById.get(id);
    const checks=[{name:station?.name || 'Ground station', value:r?.visibility}];
    checks.push({name:landingSite?.name || 'Mission site not loaded', value:r?.location_visibility?.mission});
    const failed=checks.filter(check => check.value?.visible === false);
    const unknown=!r || !!r.error || checks.some(check => !check.value);
    return {id, r, checks, status:failed.length ? 'mismatch' : unknown ? 'unknown' : 'match'};
  });
}
function renderComparison() {
  const rows=comparisonRecords();
  const bad=rows.filter(r=>r.status==='mismatch').length;
  const unknown=rows.filter(r=>r.status==='unknown').length;
  $('comparisonSummary').textContent=dataTimeMs === null ? 'Waiting' : `${bad} conflicts · ${unknown} unknown`;
  $('comparisonTime').textContent=dataTimeMs === null ? 'Waiting for propagated positions.' : `Positions: ${fmtDate(dataTimeMs)} ${fmtTime(dataTimeMs)} · active schedule assignments · mask 3°`;
  $('comparisonRows').innerHTML=rows.length ? rows.map(row => {
    const color=row.status==='match' ? 'green' : row.status==='mismatch' ? 'red' : 'orange';
    const details=row.checks.map(check => `${escapeHtml(check.name)}: ${check.value ? `${Number(check.value.elevation_deg).toFixed(2)}° ${check.value.visible ? 'visible' : 'BELOW MASK'}` : 'unknown'}`).join('<br>');
    const source=row.r?.source_file ? String(row.r.source_file).split(/[\\/]/).pop() : 'unknown';
    return `<div class="comparison-row"><button data-comparison="${escapeHtml(row.id)}">${escapeHtml(satelliteLabel(row.id))}</button> <span class="pill ${color}">${row.status.toUpperCase()}</span><div class="panel-note">${details}<br>TLE: ${escapeHtml(source)} · epoch ${escapeHtml(row.r?.tle_epoch_utc || 'unknown')}${row.r?.error ? `<br>${escapeHtml(row.r.error)}` : ''}</div></div>`;
  }).join('') : `<div class="comparison-row panel-note">${dataTimeMs === null ? 'Waiting for positions.' : 'No assignments active at this timestamp.'}</div>`;
}
function updateEventLocations() {
  const locations=coverageLocations();
  const key=JSON.stringify(locations.map(p=>[p.id,p.name]));
  if (key===navigationLocationsKey) return;
  navigationLocationsKey=key;
  const selected=$('eventLocation').value || 'all';
  $('eventLocation').innerHTML='<option value="all">All monitored locations</option>'+locations.map(p=>`<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join('');
  $('eventLocation').value=selected==='all' || locations.some(p=>p.id===selected) ? selected : 'all';
}
function setNavigationBusy(busy) {
  $('previousCoverage').disabled=busy;
  $('nextCoverage').disabled=busy;
  $('cancelCoverageSearch').hidden=!busy;
}
function cancelCoverageNavigation(message='Search cancelled because the simulation time changed.') {
  if (activeNavigationId !== null) pendingNavigationCommand={action:'cancel', id:activeNavigationId};
  activeNavigationId=null;
  setNavigationBusy(false);
  if (message) $('eventStatus').textContent=message;
}
function jumpToSimulationTime(timeMs) {
  if (!schedule || !Number.isFinite(timeMs)) return;
  cancelCoverageNavigation('');
  playing=false;
  $('playButton').textContent='▶ PLAY';
  simTimeMs=Math.max(schedule.startMs,Math.min(schedule.endMs,timeMs));
  updateClock();renderSchedule();refreshDashboard();requestOrbitUpdate(true);
}
function jumpAssignment(direction) {
  if (!schedule) { $('eventStatus').textContent='Load a schedule first.';return; }
  const starts=[...new Set(schedule.assignments.map(a=>a.startMs))].sort((a,b)=>a-b);
  const time=direction>0 ? starts.find(t=>t>simTimeMs) : starts.reverse().find(t=>t<simTimeMs);
  if (time===undefined) { $('eventStatus').textContent=`No ${direction>0 ? 'next' : 'previous'} assignment start in this schedule.`;return; }
  const ids=[...new Set(schedule.assignments.filter(a=>a.startMs===time).map(a=>a.satellite_id))];
  jumpToSimulationTime(time);
  if(ids.length) selectSatellite(String(ids[0]));
  $('eventStatus').textContent=`Assignment start: ${ids.map(satelliteLabel).join(', ')} · ${fmtDate(time)} ${fmtTime(time)}`;
}
function requestCoverageNavigation(direction) {
  if (!schedule) { $('eventStatus').textContent='Load a schedule first.';return; }
  if (!coverageLocations().length) { $('eventStatus').textContent='Add a monitoring location first.';return; }
  playing=false;$('playButton').textContent='▶ PLAY';
  activeNavigationId=++navigationSequence;
  pendingNavigationCommand={action:'coverage',id:activeNavigationId,originMs:simTimeMs,direction,
    locationId:$('eventLocation').value || 'all',kind:$('eventKind').value || 'any'};
  setNavigationBusy(true);
  $('eventStatus').textContent='Searching scheduled tracking coverage…';
}
function getSimulationRequest() {
  const command=pendingNavigationCommand;
  pendingNavigationCommand=null;
  return {time:getSimulationTime(), command};
}
function updateNavigationProgress(id,timeMs) {
  if (activeNavigationId!==id) return;
  $('eventStatus').textContent=`Searching… ${fmtDate(timeMs)} ${fmtTime(timeMs)}. You can cancel.`;
}
function finishCoverageNavigation(result) {
  if (result.id!==activeNavigationId) return;
  activeNavigationId=null;setNavigationBusy(false);
  if(result.status==='found') {
    jumpToSimulationTime(result.timeMs);
    const text=result.events.map(event=>`${event.locationName}: ${event.kind==='loss' ? 'coverage loss' : 'coverage recovery'} ${event.beforeCount} → ${event.afterCount}`).join('; ');
    $('eventStatus').textContent=`${text} · ${fmtDate(result.timeMs)} ${fmtTime(result.timeMs)} (sampled search, refined to ≤1s).${result.unknownSamples ? ' Some samples had unavailable visibility; other events may be unresolved.' : ''}`;
  } else if(result.status==='none') {
    $('eventStatus').textContent=`No matching threshold crossing found in this direction within the schedule. Search samples every 10s; shorter excursions may be missed.${result.unknownSamples ? ' Some visibility samples were unavailable.' : ''}`;
  } else $('eventStatus').textContent=result.message || 'Coverage search cancelled.';
}
function refreshDashboard() {
  updateExtraWidgets();
  const usable = orbitResults.filter(r => !r.error && Array.isArray(r.ecef_km) && r.ecef_km.length >= 3 && r.ecef_km.every(Number.isFinite));
  const displayed = usable.filter(r => layerVisible(r, "marker"));
  const visible = displayed.filter(r => r.visibility?.visible);
  $("mPositions").textContent = `${displayed.length}/${orbitResults.length}`;
  const mutual = displayed.filter(r => r.visibility?.visible && r.location_visibility?.mission?.visible);
  $("mMutual").textContent = landingSite && dataTimeMs !== null ? mutual.length : "—";
  const mutualUnknown = displayed.filter(r => !r.visibility || !r.location_visibility?.mission).length;
  $("mMutualNote").textContent = !landingSite ? "No mission site loaded" :
    `Station + ${landingSite.name || 'mission'}${mutualUnknown ? ` · ${mutualUnknown} unknown` : ''}`;
  $("mMutual").title = "Displayed satellites above 3° at BOTH station and mission site; follows the current display filter and satellite ON switches.";
  $("globeInfo").textContent = `${displayed.length} plotted · ${visible.length} station-visible`;
  const warnings = (schedule?.satellite_ids || []).filter(id => {
    const r = orbitById.get(String(id)) || {satellite_id:String(id)};
    return satelliteState(r).warning;
  });
  $("trackingWarning").hidden = warnings.length === 0;
  $("trackingWarning").textContent = `TRACKING WARNING: ${warnings.map(id => satelliteLabel(id)).join(", ")} assigned now but below the station's 3° mask or missing visibility data. Red on the globe. Visibility timestamp: ${dataTimeMs === null ? 'waiting' : fmtTime(dataTimeMs)}.`;
  renderSatelliteLayers();
  renderLocationCoverage();
  renderComparison();
  renderAdditionalPanels();
  updateEventLocations();
  renderInspector();
  drawGlobe();
}
function interpolateAtDepthZero(a, b) {
  const fraction = a.depth / (a.depth - b.depth);
  return {x: a.x + (b.x-a.x)*fraction,
          y: a.y + (b.y-a.y)*fraction, depth: 0};
}
// Clip a projected line to either hemisphere, including the limb intersection.
function hemisphereSegment(a, b, front) {
  if (!a || !b) return null;
  const aInside = front ? a.depth >= 0 : a.depth <= 0;
  const bInside = front ? b.depth >= 0 : b.depth <= 0;
  if (!aInside && !bInside) return null;
  if (aInside && bInside) return [a, b];
  const crossing = interpolateAtDepthZero(a, b);
  return aInside ? [a, crossing] : [crossing, b];
}

// NASA Earth texture, embedded by Python for offline use.
const earthTexture = new Image();
let earthTexturePixels = null;
let earthTextureWidth = 0;
let earthTextureHeight = 0;

const earthTextureCanvas = document.createElement("canvas");
const earthTextureCtx = earthTextureCanvas.getContext("2d", {
    willReadFrequently: true
});

const earthRenderCanvas = document.createElement("canvas");
const earthRenderCtx = earthRenderCanvas.getContext("2d");

const earthTextureBase64 = "__EARTH_TEXTURE_BASE64__";

if (earthTextureBase64.length > 0) {
    earthTexture.onload = () => {
        // Downsample the source texture for responsive rotation.
        earthTextureWidth = 2048;
        earthTextureHeight = 1024;

        earthTextureCanvas.width = earthTextureWidth;
        earthTextureCanvas.height = earthTextureHeight;

        earthTextureCtx.drawImage(
            earthTexture,
            0,
            0,
            earthTextureWidth,
            earthTextureHeight
        );

        earthTexturePixels = earthTextureCtx.getImageData(
            0,
            0,
            earthTextureWidth,
            earthTextureHeight
        ).data;

        console.log("NASA Earth texture loaded.");
        if (typeof drawGlobe === "function") {
            drawGlobe();
        }
    };

    earthTexture.onerror = () => {
        console.error("Could not load the embedded Earth texture.");
    };

    earthTexture.src =
        "data:image/jpeg;base64," + earthTextureBase64;
}
let globeDragging = false;
let globeLastX = 0;
let globeLastY = 0;
let globeMoved = false;

function fmtTime(ms) {
  if (!Number.isFinite(ms)) return "—";
  return new Date(ms).toISOString().slice(11,19) + " UTC";
}
function fmtDate(ms) {
  if (!Number.isFinite(ms)) return "—";
  return new Date(ms).toISOString().slice(0,10);
}
function fmtDuration(seconds) {
  seconds = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(seconds/3600);
  const m = Math.floor((seconds%3600)/60);
  const s = seconds%60;
  return h ? `${h}h ${m}m` : `${m}m ${s}s`;
}
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function setStatus(text, state="wait") {
  $("statusText").textContent = text;
  $("statusDot").className = "dot" + (state==="good" ? " good" : state==="bad" ? " bad" : "");
}
function addDiagnostic(title, message, type="info") {
  const key = `${title}|${message}`;
  if (diagnostics.some(d => d.key === key)) return;
  diagnostics.unshift({key,title,message,type, recordedUTC:new Date().toISOString(), simulationUTC:Number.isFinite(simTimeMs) ? new Date(simTimeMs).toISOString() : null});
  diagnostics = diagnostics.slice(0,1000);
  renderDiagnostics();
}
function renderDiagnostics() {
  $("diagCount").textContent = `${diagnostics.length} messages`;
  $("diagnostics").innerHTML = diagnostics.length
    ? diagnostics.map(d => `<div class="diag">
        <div class="diag-title"><span class="pill ${d.type==="error"?"red":d.type==="warn"?"orange":"blue"}">${escapeHtml(d.type.toUpperCase())}</span> ${escapeHtml(d.title)}</div>
        <div class="diag-text">Logged ${escapeHtml(d.recordedUTC || "earlier session")}${d.simulationUTC ? ` · Simulation ${escapeHtml(d.simulationUTC)}` : ""}</div>
        <div class="diag-text">${escapeHtml(d.message)}</div></div>`).join("")
    : '<div class="diag-text">No diagnostics yet.</div>';
}
function assignmentActive(a, t=simTimeMs) {
  return Number.isFinite(a.startMs) && Number.isFinite(a.endMs) &&
    t >= a.startMs && t < a.endMs;
}
function loadSchedule(data) {
  cancelCoverageNavigation('Choose an assignment or coverage event.');
  schedule = data;
  // Each imported schedule starts with only its assigned satellites shown.
  satelliteFilter = "scheduled";
  $("satelliteFilter").value = "scheduled";
  dataTimeMs = null;
  layerTableKey = "";
  selectedId = null;
  // Discard results from the previous schedule until Python refreshes them.
  orbitResults = [];
  orbitById = new Map();
  simTimeMs = data.startMs;
  playing = false;
  $("playButton").textContent = "▶ PLAY";
  $("timeline").value = 0;
  $("timeline").disabled = !(data.endMs > data.startMs);
  $("mSatellites").textContent = (data.satellite_ids || []).length;
  $("mDuration").textContent = fmtDuration((data.endMs-data.startMs)/1000);
  $("mDurationRange").innerHTML = `${fmtDate(data.startMs)} ${fmtTime(data.startMs)}<br>→ ${fmtDate(data.endMs)} ${fmtTime(data.endMs)}`;
  $("assignmentCount").textContent = `${data.assignments.length} rows`;
  $("rangeStart").textContent = `${fmtDate(data.startMs)} ${fmtTime(data.startMs)}`;
  $("rangeEnd").textContent = `${fmtDate(data.endMs)} ${fmtTime(data.endMs)}`;
  $("globeInfo").textContent = `${data.assignments.length} assignments · UTC`;
  $("footerLeft").textContent = "SGP4 PROPAGATION · APPROXIMATE TEME → ECEF ROTATION";
  $("footerRight").textContent = "GEOMETRIC LINE-OF-SIGHT · ELEVATION MASK 3°";
  activeIssues.clear();
  addDiagnostic("Schedule loaded", `${data.source} · ${data.assignments.length} assignments · ${(data.satellite_ids||[]).length} unique satellites`);
  (data.warnings || []).forEach(w => addDiagnostic("Schedule warning",w,"warn"));
  renderSchedule();
  updateClock();
  setOrbitData([]);
}
function renderSchedule() {
  if (!schedule) return;
  $("scheduleRows").innerHTML = schedule.assignments.map((a,i) => {
    const state = assignmentActive(a) ? '<span class="pill green">ACTIVE</span>' :
      simTimeMs < a.startMs ? '<span class="pill blue">UPCOMING</span>' :
      '<span class="pill orange">ENDED</span>';
    return `<tr class="${selectedId===a.satellite_id?'selected':''}" onclick="selectSatellite('${escapeHtml(a.satellite_id)}')">
      <td class="mono" title="${escapeHtml(labelDescription(a.satellite_id))}">${escapeHtml(satelliteLabel(a.satellite_id))}</td>
      <td class="mono">${fmtTime(a.startMs)}</td><td>${state}</td></tr>`;
  }).join("");
}
function selectSatellite(id) {
  selectedId = String(id);
  renderSchedule();
  layerTableKey = "";
  refreshDashboard();
}
function renderInspector() {
  const r = orbitById.get(selectedId);
  const assignments = schedule ? schedule.assignments.filter(a=>a.satellite_id===selectedId) : [];
  if (!selectedId) {
    $("satDetail").innerHTML = '<div class="diag-text">Select a satellite assignment.</div>';
    return;
  }
  if (!r) {
    $("satDetail").innerHTML = `<div class="detail-title">${escapeHtml(satelliteLabel(selectedId))} <span class="panel-note">NORAD ${escapeHtml(selectedId)}</span></div>
      <div class="panel-note">MEOSAR ${escapeHtml(metadataFor(selectedId).meosar_id || 'Unknown')} · Band ${escapeHtml(metadataFor(selectedId).band || 'Unknown')}</div>
      <div class="pill red">NO PROPAGATED POSITION</div>
      <div class="diag-text" style="margin-top:9px">The orbit engine did not return a usable position for this satellite at the selected time. Check TLE availability and diagnostics.</div>`;
    return;
  }
  if (r.error) {
    $("satDetail").innerHTML = `<div class="detail-title">${escapeHtml(satelliteLabel(selectedId))} <span class="panel-note">NORAD ${escapeHtml(selectedId)}</span></div>
      <div class="panel-note">MEOSAR ${escapeHtml(metadataFor(selectedId).meosar_id || 'Unknown')} · Band ${escapeHtml(metadataFor(selectedId).band || 'Unknown')}</div>
      <div class="pill red">PROPAGATION ERROR</div><div class="diag-text" style="margin-top:9px">${escapeHtml(r.error)}</div>`;
    return;
  }
  const e = r.ecef_km;
  const p = r.subpoint || {};
  const vis = r.visibility;
  const state = satelliteState(r);
  $("satDetail").innerHTML = `<div class="detail-title">${escapeHtml(satelliteLabel(selectedId))} <span class="panel-note">NORAD ${escapeHtml(selectedId)}</span></div>
    <div style="color:${state.color};margin-bottom:8px;font-weight:700">${escapeHtml(state.label)}</div>
    ${state.warning ? '<div class="diag-text" style="color:var(--red);margin-bottom:8px">Assigned for tracking now, but not confirmed visible above the ground station’s 3° mask. Check time, TLE, and station coordinates.</div>' : ''}
    <div class="detail-grid">
      <div><div class="detail-label">NORAD ID</div><div class="detail-value mono">${escapeHtml(selectedId)}</div></div>
      <div><div class="detail-label">MEOSAR ID</div><div class="detail-value mono">${escapeHtml(metadataFor(selectedId).meosar_id || 'Unknown')}</div></div>
      <div><div class="detail-label">Band</div><div class="detail-value">${escapeHtml(metadataFor(selectedId).band || 'Unknown')}</div></div>
      <div><div class="detail-label">Visibility</div><div class="detail-value">${vis ? `<span class="pill ${vis.visible?'green':'red'}">${vis.visible?'VISIBLE':'NOT VISIBLE'}</span>`:'UNKNOWN'}</div></div>
      <div><div class="detail-label">Elevation</div><div class="detail-value">${vis && Number.isFinite(vis.elevation_deg)?vis.elevation_deg.toFixed(2)+'°':'—'}</div></div>
      <div><div class="detail-label">Subpoint latitude</div><div class="detail-value">${Number.isFinite(p.latitude)?p.latitude.toFixed(3)+'°':'—'}</div></div>
      <div><div class="detail-label">Subpoint longitude</div><div class="detail-value">${Number.isFinite(p.longitude)?p.longitude.toFixed(3)+'°':'—'}</div></div>
      <div><div class="detail-label">Altitude</div><div class="detail-value">${Number.isFinite(p.altitude_km)?p.altitude_km.toFixed(1)+' km':'—'}</div></div>
      <div><div class="detail-label">TLE age</div><div class="detail-value">${Number.isFinite(r.tle_age_hours)?(r.tle_age_hours/24).toFixed(1)+' days':'—'}</div></div>
      <div><div class="detail-label">ECEF X / Y / Z</div><div class="detail-value mono">${e?e.map(v=>Number(v).toFixed(0)).join(' / ')+' km':'—'}</div></div>
      <div><div class="detail-label">Assignments</div><div class="detail-value">${assignments.length}</div></div>
    </div>
    ${r.tle_age_warning?`<div class="diag-text" style="margin-top:10px;color:var(--orange)">${escapeHtml(r.tle_age_warning)}</div>`:''}`;
}
function updateClock() {
  $("timeText").textContent = fmtTime(simTimeMs);
  $("dateText").textContent = fmtDate(simTimeMs) + " · UTC";
  if (schedule && schedule.endMs > schedule.startMs) {
    $("timeline").value = Math.round(1000*(simTimeMs-schedule.startMs)/(schedule.endMs-schedule.startMs));
  }
}
function togglePlay() {
  cancelCoverageNavigation('');
  if (!schedule) return;
  if (simTimeMs >= schedule.endMs) simTimeMs = schedule.startMs;
  playing = !playing;
  $("playButton").textContent = playing ? "Ⅱ PAUSE" : "▶ PLAY";
  lastFrame = 0;
}
function setSpeed(value) { speed = Number(value) || 1; }
function step(seconds) {
  if (!schedule) return;
  cancelCoverageNavigation();
  playing = false;
  $("playButton").textContent = "▶ PLAY";
  simTimeMs = Math.max(schedule.startMs,Math.min(schedule.endMs,simTimeMs+seconds*1000));
  updateClock(); renderSchedule(); refreshDashboard(); requestOrbitUpdate(true);
}
function seek(value) {
  if (!schedule) return;
  cancelCoverageNavigation();
  const f = Number(value)/1000;
  simTimeMs = schedule.startMs + (schedule.endMs-schedule.startMs)*f;
  updateClock(); renderSchedule(); refreshDashboard(); requestOrbitUpdate(true);
}
function getSimulationTime() { return new Date(simTimeMs).toISOString(); }


const activeIssues = new Map();
function updateIssueHistory() {
  const current = new Map();
  for (const r of orbitResults) {
    const id=String(r.satellite_id || r.norad_id || '?');
    if (r.error) current.set(`propagation:${id}`, `Satellite ${satelliteLabel(id)}: ${r.error}`);
    if (r.visibility_error) current.set(`visibility:${id}`, `Satellite ${satelliteLabel(id)}: ${r.visibility_error}`);
    if (r.tle_age_warning) current.set(`tle:${id}`, `Satellite ${satelliteLabel(id)}: ${r.tle_age_warning}`);
  }
  for (const row of comparisonRecords()) {
    if (row.status !== 'match') current.set(`assignment:${row.id}`,
      `${satelliteLabel(row.id)} assigned: ${row.status === 'unknown' ? 'visibility unavailable' : row.checks.filter(c=>c.value?.visible===false).map(c=>`${c.name} ${Number(c.value.elevation_deg).toFixed(2)}° below 3°`).join('; ')}`);
  }
  function record(title,message,type) {
    diagnostics.unshift({key:`${Date.now()}-${Math.random()}`,title,message,type,
      recordedUTC:new Date().toISOString(),simulationUTC:dataTimeMs===null?null:new Date(dataTimeMs).toISOString()});
  }
  for (const [key,message] of current) if (!activeIssues.has(key) || activeIssues.get(key)!==message) {
    // Elevation changes do not generate a new row every frame.
    if (!activeIssues.has(key)) record('Warning',message,'warn');
  }
  for (const [key,message] of activeIssues) if (!current.has(key)) {
    const id=key.split(':').slice(1).join(':');
    const r=orbitById.get(id);
    const resolved = key.startsWith('assignment:') ? comparisonRecords().some(row=>row.id===id && row.status==='match') :
      !!r && !r.error && (!key.startsWith('visibility:') || !!r.visibility);
    record(resolved ? 'Resolved' : 'No longer evaluated',message,'info');
  }
  activeIssues.clear(); for (const entry of current) activeIssues.set(...entry);
  diagnostics=diagnostics.slice(0,1000); renderDiagnostics();
}
