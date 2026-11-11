const dashboardWidgets = [
 ['scheduled','Scheduled satellites','mSatellites'], ['positions','Positions available','mPositions'],
 ['mutual','Mutually visible (displayed)','mMutual'], ['duration','Duration and date range','mDuration'],
 ['tracked','Currently tracked','mActiveWidget'], ['conflicts','Assignment conflicts','mConflictWidget'],
 ['pins','Pins below three tracked','mPinsWidget'],
 ['station','Visible from station (library)','mStationWidget'],
 ['tle','TLE warnings','mTleWidget'], ['next','Next assignment UTC','mNextWidget'],
 ['clock','Simulation UTC','mClockWidget'], ['speed','Playback speed','mSpeedWidget'],
 ['unknown','Assignment visibility unknown','mUnknownWidget'],
 ['antennas','Antennas assigned now','mAntennaWidget'],
 ['progress','Simulation progress','mProgressWidget'],
 ['remaining','Simulation time remaining','mRemainingWidget'],
 ['handoff','Next assignment change','mHandoffWidget'],
 ['oldest','Oldest loaded TLE age','mOldestWidget'],
 ['coveragefloor','Lowest tracked location count','mCoverageFloorWidget']
];
const dashboardDefaults=['scheduled','positions','mutual','duration'];
let dashboardSelection=[...dashboardDefaults];
let dashboardLabels={};
let dashboardObserver=null;
function dashboardCatalog() {
  return [...dashboardWidgets,...pinnedLocations.map(p=>['pin:'+String(p.id),p.name+' tracked coverage','mPin_'+String(p.id)])];
}
function applyDashboardOptions() {
  const grid=document.querySelector('.metrics'),catalog=dashboardCatalog();
  for(const [key,label,id] of catalog) {
    let value=$(id);
    if(!value) {
      const box=document.createElement('div');box.className='metric';
      const heading=document.createElement('div');heading.className='metric-label';box.appendChild(heading);
      value=document.createElement('div');value.className='metric-value cyan';value.id=id;value.textContent='—';box.appendChild(value);grid.appendChild(box);
    }
    const tile=value.closest('.metric');tile.dataset.widgetKey=key;
    tile.querySelector('.metric-label').textContent=dashboardLabels[key]||label;
    tile.style.display=dashboardSelection.includes(key)?'':'none';
    tile.style.minWidth='0';
  }
  for(const tile of grid.querySelectorAll('.metric')) {
    if(!catalog.some(w=>w[0]===tile.dataset.widgetKey)) tile.style.display='none';
  }
  // Physically reorder cards so visual and keyboard reading order match.
  for(const key of dashboardSelection) {
    const entry=catalog.find(w=>w[0]===key);if(entry)grid.appendChild($(entry[2]).closest('.metric'));
  }
  grid.style.display=dashboardSelection.some(key=>catalog.some(w=>w[0]===key))?'grid':'none';
  grid.style.gridTemplateColumns='repeat(auto-fit,minmax(min(165px,100%),1fr))';
  if(typeof ResizeObserver!=='undefined') {
    if(!dashboardObserver) dashboardObserver=new ResizeObserver(entries=>{
      for(const entry of entries) {
        const value=entry.target.querySelector('.metric-value');
        if(value)value.style.fontSize=Math.max(14,Math.min(24,entry.contentRect.width/8))+'px';
      }
    });
    dashboardObserver.disconnect();grid.querySelectorAll('.metric').forEach(tile=>dashboardObserver.observe(tile));
  }
  queueGlobeDraw();
}
const sidebarWidgets=[
 ['comparisonPanel','Scheduler / simulator check'],['coveragePanel','Location coverage'],
 ['satelliteControlsPanel','Satellite layers'],['schedulePanel','Assignment timeline'],
 ['satPanel','Satellite inspector'],['diagnosticPanel','Engine diagnostics'],
 ['activeContactsPanel','Active antenna contacts'],['upcomingContactsPanel','Upcoming assignments'],
 ['dataHealthPanel','Data health'],['coverageSummaryPanel','Coverage summary']
];
const sidebarDefaults=['comparisonPanel','coveragePanel','satelliteControlsPanel','schedulePanel','satPanel','diagnosticPanel'];
let sidebarSelection=[...sidebarDefaults];
let sidebarLabels={};
function applySidebarOptions() {
  const aside=document.querySelector('aside.right');
  for(const [key,label] of sidebarWidgets) {
    const panel=$(key);if(!panel)continue;
    panel.style.display=sidebarSelection.includes(key)?'flex':'none';
    const heading=panel.querySelector('.panel-title');
    if(heading){heading.textContent=sidebarLabels[key]||label;heading.title=label;}
    panel.style.flex='1 0 180px';
    panel.style.minHeight='150px';
  }
  // Keep tracking warnings at the top regardless of panel visibility choices.
  if($('trackingWarning'))aside.prepend($('trackingWarning'));
  for(const key of sidebarSelection)if($(key))aside.appendChild($(key));
  queueGlobeDraw();
}
function openDashboardOptions() {
  let dialog=$('dashboardOptions');if(dialog)dialog.remove();
  dialog=document.createElement('dialog');dialog.id='dashboardOptions';
  dialog.style.cssText='background:#0c1929;color:#e8f2ff;border:1px solid #294d68;border-radius:10px;padding:22px;width:min(1100px,92vw);max-height:85vh;overflow:auto';
  dialog.innerHTML='<h3 style="color:#65e4ff;margin-top:0">CUSTOMIZE DASHBOARD</h3><p>Customize each area independently. Use the arrows to reorder, edit titles, and add or remove information.</p><div id="dashboardEditors" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(360px,100%),1fr));gap:24px"></div><div style="display:flex;gap:8px;margin-top:18px"><span style="flex:1"></span><button id="dashboardCancel">CANCEL</button><button id="dashboardSave">SAVE BOTH AREAS</button></div>';
  document.body.appendChild(dialog);
  const drafts=[];
  function editor(title,description,catalog,selection,savedLabels,defaults) {
    const draft=[...selection],labels={...savedLabels};
    const section=document.createElement('section');section.style.cssText='min-width:0;border:1px solid #29465d;border-radius:7px;padding:12px';
    const heading=document.createElement('h4');heading.textContent=title;heading.style.color='#65e4ff';section.appendChild(heading);
    const note=document.createElement('p');note.textContent=description;note.style.cssText='font-size:12px;color:#9db5ca';section.appendChild(note);
    const rows=document.createElement('div');section.appendChild(rows);
    const addRow=document.createElement('div');addRow.style.cssText='display:flex;gap:8px;margin-top:12px';
    const picker=document.createElement('select');picker.style.cssText='min-width:0;flex:1';addRow.appendChild(picker);
    const add=document.createElement('button');add.textContent='ADD';addRow.appendChild(add);section.appendChild(addRow);
    const reset=document.createElement('button');reset.textContent='RESET THIS AREA';reset.style.marginTop='12px';section.appendChild(reset);
    const nameFor=key=>catalog.find(w=>w[0]===key)?.[1]||'Unavailable location: '+key;
    function render() {
      rows.replaceChildren();
      draft.forEach((key,index)=>{
        const row=document.createElement('div');row.style.cssText='display:flex;gap:6px;align-items:center;padding:8px 0;border-bottom:1px solid #263e54';
        const information=document.createElement('div');information.style.cssText='flex:1;min-width:0';
        const small=document.createElement('div');small.style.cssText='font-size:10px;color:#829fb9;margin-bottom:5px';small.textContent=nameFor(key);information.appendChild(small);
        const input=document.createElement('input');input.value=labels[key]||nameFor(key);input.maxLength=70;input.setAttribute('aria-label',title+' title');input.style.cssText='box-sizing:border-box;width:100%;background:#14283c;color:#dceeff;border:1px solid #31546d;padding:6px';
        input.oninput=()=>{labels[key]=input.value.trim();};information.appendChild(input);row.appendChild(information);
        for(const [label,action,disabled] of [
          ['↑',()=>{[draft[index-1],draft[index]]=[draft[index],draft[index-1]];render();},index===0],
          ['↓',()=>{[draft[index+1],draft[index]]=[draft[index],draft[index+1]];render();},index===draft.length-1],
          ['×',()=>{draft.splice(index,1);render();},false]
        ]) {const button=document.createElement('button');button.textContent=label;button.disabled=disabled;button.title=label==='×'?'Remove':label==='↑'?'Move up':'Move down';button.onclick=action;row.appendChild(button);}
        rows.appendChild(row);
      });
      if(!draft.length)rows.textContent='No items selected. Add one below to restore it.';
      picker.replaceChildren();
      for(const [key,label] of catalog.filter(w=>!draft.includes(w[0]))) {
        const option=document.createElement('option');option.value=key;option.textContent=label;picker.appendChild(option);
      }
      add.disabled=picker.options.length===0;
    }
    add.onclick=()=>{if(picker.value){draft.push(picker.value);render();}};
    reset.onclick=()=>{draft.splice(0,draft.length,...defaults);Object.keys(labels).forEach(k=>delete labels[k]);render();};
    $('dashboardEditors').appendChild(section);render();return {draft,labels};
  }
  const top=editor('ABOVE GLOBE','Information tiles above the Earth.',dashboardCatalog(),dashboardSelection,dashboardLabels,dashboardDefaults);
  const right=editor('RIGHT SIDEBAR','Coverage, layers, contacts, inspector and diagnostics panels.',sidebarWidgets,sidebarSelection,sidebarLabels,sidebarDefaults);
  $('dashboardCancel').onclick=()=>dialog.close();
  $('dashboardSave').onclick=()=>{
    dashboardSelection=[...top.draft];dashboardLabels={...top.labels};
    sidebarSelection=[...right.draft];sidebarLabels={...right.labels};
    applyDashboardOptions();applySidebarOptions();updateExtraWidgets();dialog.close();
  };
  dialog.showModal();
}

function dashboardStateJSON() {return JSON.stringify({widgets:dashboardSelection,widgetLabels:dashboardLabels,sidebarWidgets:sidebarSelection,sidebarLabels:sidebarLabels,diagnostics:diagnostics.slice(0,1000)});}
function restoreDashboardState(state) {
  if(Array.isArray(state.widgets)) dashboardSelection=[...new Set(state.widgets.filter(k=>typeof k==='string' && (dashboardWidgets.some(w=>w[0]===k)||k.startsWith('pin:'))))];
  if(state.widgetLabels && typeof state.widgetLabels==='object' && !Array.isArray(state.widgetLabels)) {
    dashboardLabels=Object.fromEntries(Object.entries(state.widgetLabels).filter(([key,value])=>typeof value==='string').map(([key,value])=>[key,value.slice(0,70)]));
  }
  if(Array.isArray(state.sidebarWidgets)) sidebarSelection=[...new Set(state.sidebarWidgets.filter(key=>sidebarWidgets.some(w=>w[0]===key)))];
  if(state.sidebarLabels && typeof state.sidebarLabels==='object' && !Array.isArray(state.sidebarLabels)) {
    sidebarLabels=Object.fromEntries(Object.entries(state.sidebarLabels).filter(([key,value])=>sidebarWidgets.some(w=>w[0]===key)&&typeof value==='string').map(([key,value])=>[key,value.slice(0,70)]));
  }
  if(Array.isArray(state.diagnostics))diagnostics=[...diagnostics,...state.diagnostics].slice(0,1000);
  applyDashboardOptions();applySidebarOptions();renderDiagnostics();
}

function contactAntenna(a) {return String(a.antenna??a.antenna_id??a.field_3??'?');}
function compareContactAntennas(a,b) {
  const av=contactAntenna(a),bv=contactAntenna(b);
  if(av==='?'||bv==='?')return av===bv?0:av==='?'?1:-1;
  return av.localeCompare(bv,undefined,{numeric:true})||String(a.satellite_id).localeCompare(String(b.satellite_id),undefined,{numeric:true});
}
function dashboardDuration(seconds) {
  seconds=Math.max(0,Math.floor(seconds));
  const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),ss=seconds%60;
  return (h?h+'h ':'')+m+'m '+String(ss).padStart(2,'0')+'s';
}
function dashboardCoverage() {
  const now=dataTimeMs??simTimeMs;
  const ids=[...new Set((schedule?.assignments||[]).filter(a=>assignmentActive(a,now)).map(a=>String(a.satellite_id)))];
  return coverageLocations().map(p=>{
    const views=ids.map(id=>orbitById.get(id)?.location_visibility?.[p.id]);
    return {...p,count:views.filter(v=>v?.visible===true).length,unknown:views.filter(v=>!v).length};
  });
}
function renderAdditionalPanels() {
  const now=dataTimeMs??simTimeMs;
  const active=(schedule?.assignments||[]).filter(a=>assignmentActive(a,now)).sort(compareContactAntennas);
  const row=(title,detail)=>`<div class="coverage-row"><div>${title}</div><div class="panel-note" style="margin-top:5px;line-height:1.6">${detail}</div></div>`;
  const activePanel=$('activeContactsPanel');
  if(activePanel.style.display!=='none') $('activeContactsRows').innerHTML=active.length?active.map(a=>{
    const id=String(a.satellite_id),meta=metadataFor(id),r=orbitById.get(id);
    const status=!r||r.error||!r.visibility?'Unknown station visibility':r.visibility.visible?'Station visible':'Below station mask';
    return row(`ANT ${escapeHtml(contactAntenna(a))} · <button class="action" data-contact-select="${escapeHtml(id)}">${escapeHtml(satelliteLabel(id))}</button>`,
      `MEOSAR ${escapeHtml(meta.meosar_id||'?')} · NORAD ${escapeHtml(id)} · ${escapeHtml(meta.band||'?')} band<br>${fmtTime(a.startMs)} → ${fmtTime(a.endMs)}<br>${dashboardDuration((a.endMs-now)/1000)} remaining / ${dashboardDuration((a.endMs-a.startMs)/1000)} total<br>${status}`);
  }).join(''):'<div class="coverage-note">No active contacts at the current data timestamp.</div>';
  if($('upcomingContactsPanel').style.display!=='none') {
    const upcoming=(schedule?.assignments||[]).filter(a=>a.startMs>simTimeMs).sort((a,b)=>a.startMs-b.startMs||compareContactAntennas(a,b));
    $('upcomingContactsRows').innerHTML=upcoming.slice(0,8).map(a=>row(`${escapeHtml(satelliteLabel(String(a.satellite_id)))} · ANT ${escapeHtml(contactAntenna(a))}`,
      `${fmtDate(a.startMs)} ${fmtTime(a.startMs)}<br>In ${dashboardDuration((a.startMs-simTimeMs)/1000)} · ${dashboardDuration((a.endMs-a.startMs)/1000)} duration<br><button class="action" data-contact-time="${Number(a.startMs)}">JUMP TO START</button>`)).join('')+(upcoming.length>8?`<div class="coverage-note">${upcoming.length-8} more assignments</div>`:'')||'<div class="coverage-note">No upcoming assignments.</div>';
  }
  if($('dataHealthPanel').style.display!=='none') {
    const errors=orbitResults.filter(r=>r.error),warnings=orbitResults.filter(r=>r.tle_age_warning),unknown=comparisonRecords().filter(r=>r.status==='unknown');
    $('dataHealthRows').innerHTML=row('CURRENT DATA SNAPSHOT',dataTimeMs===null?'Waiting for propagation':fmtDate(dataTimeMs)+' '+fmtTime(dataTimeMs))+row('PROPAGATION / ASSIGNMENTS',`${errors.length} propagation errors<br>${unknown.length} active assignments with unknown visibility<br>${warnings.length} TLE age warnings`)+
      [...errors.map(r=>[r,r.error]),...warnings.map(r=>[r,r.tle_age_warning])].slice(0,10).map(([r,message])=>row(escapeHtml(satelliteLabel(String(r.satellite_id??r.norad_id))),escapeHtml(message))).join('');
  }
  if($('coverageSummaryPanel').style.display!=='none') {
    $('coverageSummaryRows').innerHTML=dataTimeMs===null?'<div class="coverage-note">Waiting for propagation.</div>':dashboardCoverage().map(p=>{
      const status=p.count>=3?'3+ CONFIRMED':p.count+p.unknown>=3?'UNRESOLVED':'BELOW THREE';
      const color=p.count>=3?'#52f0b0':status==='UNRESOLVED'?'#91a4b8':'#ffad5b';
      return row(`<span style="color:${color}">${escapeHtml(p.name)} · ${status}</span>`,`${p.count} tracked and visible${p.unknown?' · '+p.unknown+' unknown':''}<br>Data time: ${fmtTime(dataTimeMs)}`);
    }).join('');
  }
}

function updateExtraWidgets() {
  const catalog=dashboardCatalog();
  const grid=document.querySelector('.metrics');
  const signature=JSON.stringify(catalog.map(w=>w[0]));
  if(grid.dataset.catalogSignature!==signature) {grid.dataset.catalogSignature=signature;applyDashboardOptions();}
  const now=dataTimeMs??simTimeMs;
  const activeIds=new Set((schedule?.assignments||[]).filter(a=>assignmentActive(a,now)).map(a=>String(a.satellite_id)));
  const comparisons=comparisonRecords();
  $('mActiveWidget').textContent=activeIds.size;
  $('mConflictWidget').textContent=comparisons.filter(r=>r.status==='mismatch').length;
  $('mUnknownWidget').textContent=comparisons.filter(r=>r.status==='unknown').length;
  let below=0,uncertain=0;
  for(const p of pinnedLocations) {
    const views=[...activeIds].map(id=>orbitById.get(id)?.location_visibility?.[p.id]);
    const count=views.filter(v=>v?.visible===true).length,unknown=views.filter(v=>!v).length;
    if(count<3 && count+unknown>=3)uncertain++;else if(count<3)below++;
    const value=$('mPin_'+String(p.id));if(value) {
      value.textContent=dataTimeMs===null?'—':`${count}${unknown?' + '+unknown+' unknown':''}`;
      value.style.color=count>=3?'#52f0b0':count+unknown>=3?'#91a4b8':count===2?'#ffe279':'#ffad5b';
      value.title='Actively assigned satellites geometrically visible at this location; unknown results are listed separately.';
    }
  }
  $('mPinsWidget').textContent=dataTimeMs===null?'—':pinnedLocations.length?`${below}${uncertain?' · '+uncertain+' unknown':''}`:'No pins';
  $('mStationWidget').textContent=dataTimeMs===null?'—':orbitResults.filter(r=>r.visibility?.visible===true).length;
  $('mTleWidget').textContent=dataTimeMs===null?'—':orbitResults.filter(r=>r.tle_age_warning).length;
  const next=(schedule?.assignments||[]).filter(a=>a.startMs>simTimeMs).sort((a,b)=>a.startMs-b.startMs)[0];
  $('mNextWidget').textContent=next?fmtTime(next.startMs):'No upcoming';
  $('mNextWidget').title=next?fmtDate(next.startMs)+' '+satelliteLabel(String(next.satellite_id)):'';
  $('mClockWidget').textContent=schedule?fmtTime(simTimeMs):'—';
  $('mSpeedWidget').textContent=Number(speed).toFixed(0)+'×'+(playing?' · playing':' · paused');
  const contacts=(schedule?.assignments||[]).filter(a=>assignmentActive(a,now));
  $('mAntennaWidget').textContent=schedule?new Set(contacts.map(contactAntenna).filter(a=>a!=='?')).size:'—';
  const span=schedule?Math.max(1,schedule.endMs-schedule.startMs):1;
  $('mProgressWidget').textContent=schedule?(100*Math.max(0,Math.min(1,(simTimeMs-schedule.startMs)/span))).toFixed(1)+'%':'—';
  $('mRemainingWidget').textContent=schedule?dashboardDuration((schedule.endMs-simTimeMs)/1000):'—';
  const changes=(schedule?.assignments||[]).flatMap(a=>[a.startMs,a.endMs]).filter(t=>t>simTimeMs).sort((a,b)=>a-b);
  $('mHandoffWidget').textContent=changes.length?dashboardDuration((changes[0]-simTimeMs)/1000):'No more changes';
  $('mHandoffWidget').title=changes.length?fmtDate(changes[0])+' '+fmtTime(changes[0]):'';
  const ages=orbitResults.map(r=>Number(r.tle_age_hours)).filter(Number.isFinite);
  $('mOldestWidget').textContent=ages.length?Math.max(...ages).toFixed(1)+' h':'—';
  $('mOldestWidget').title='Age relative to the propagated simulation timestamp; a negative age is a future epoch.';
  const coverage=dashboardCoverage();
  $('mCoverageFloorWidget').textContent=dataTimeMs===null||!coverage.length?'—':Math.min(...coverage.map(p=>p.count))+(coverage.some(p=>p.unknown)?' + ?':'');
  $('mCoverageFloorWidget').title='Lowest observed tracked count across station, mission site and pins. Unknown geometry may increase it.';

}


