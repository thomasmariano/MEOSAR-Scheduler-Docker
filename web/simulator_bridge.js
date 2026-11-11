/* HTTP transport for the unchanged desktop simulator dashboard. */
'use strict';
(async()=>{
  const cfg=simulatorConfig,base=`/api/jobs/${cfg.job_id}/simulation/`;
  let inFlight=false,lastKey='',lastPathKey=null,navigating=false;
  let pins=[];
  const storageKey='meosar-sim-'+cfg.job_id;
  async function call(route,body){const response=await fetch(base+route,{method:'POST',headers:{'Content-Type':'application/json','X-MEOSAR-Request':'1'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok){const error=Error(data.detail||'Simulation request failed');error.status=response.status;throw error;}return data;}
  function packet(){return {time:getSimulationTime(),revision:cfg.revision,pins:pins.map(p=>({name:p.name,latitude:p.latitude,longitude:p.longitude,elevation:p.elevation||0}))};}
  async function update(){if(window.meosarVideoBusy||inFlight||navigating||!schedule)return;const command=getSimulationRequest().command;if(command?.action==='coverage'){await navigate(command);return;}const key=JSON.stringify([getSimulationTime(),pins,showOrbitPaths,showGroundTracks]);if(key===lastKey)return;inFlight=true;try{const pathKey=Math.floor(simTimeMs/300000);const body=packet();body.paths=(showOrbitPaths||showGroundTracks)&&lastPathKey!==pathKey;const data=await call('frame',body);lastKey=key;if(!window.meosarVideoBusy){setOrbitData(data.results);if(data.paths){setOrbitPaths(data.paths);lastPathKey=pathKey;}}}catch(error){if(error.status!==429)setOrbitError(error.message);}finally{inFlight=false;}}
  async function navigate(command){navigating=true;try{const data=await call('event',{...packet(),command});finishCoverageNavigation(data);}catch(error){finishCoverageNavigation({id:command.id,status:'error',message:error.message});}finally{navigating=false;lastKey='';update();}}
  function persist(){try{localStorage.setItem(storageKey,JSON.stringify({pins,dashboard:JSON.parse(dashboardStateJSON())}));}catch{}}
  const tools=document.createElement('div');tools.className='control-row';tools.style.cssText='padding:10px 18px;display:flex;flex-wrap:wrap;gap:10px;background:#0d1b2a';
  function button(title,action){const b=document.createElement('button');b.className='action';b.textContent=title;b.onclick=action;tools.append(b);return b;}
  const back=document.createElement('a');back.href='/';back.textContent='← Scheduler';back.style.color='#7bdaff';tools.append(back);
  const title=document.createElement('span');title.className='panel-note';title.textContent=cfg.mission_name+' · '+(cfg.revision==='original'?'Original schedule':'Edited revision');tools.append(title);
  button('Dashboard',()=>openDashboardOptions());
  async function sharedApi(path,body){const response=await fetch('/api/'+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json','X-MEOSAR-Request':'1'},body:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw Error(value.detail||'Request failed.');return value;}
  const sourceCaption=document.createElement('span');sourceCaption.className='panel-note';sourceCaption.textContent='TLE: '+(cfg.tle_source||'Frozen snapshot');tools.append(sourceCaption);
  button('Load schedule / latest',async()=>{
    const modal=document.createElement('dialog');modal.style.cssText='background:#102033;color:#e5f4ff;border:1px solid #41657d;border-radius:10px;padding:20px;width:min(750px,95vw)';
    const heading=document.createElement('h3');heading.textContent='Completed schedules';modal.append(heading);const rows=document.createElement('div'),note=document.createElement('p');rows.style.maxHeight='55vh';rows.style.overflow='auto';modal.append(note,rows);
    function action(label,fn){const b=document.createElement('button');b.className='action';b.textContent=label;b.onclick=fn;modal.append(b);return b;}
    action('Close',()=>modal.close());modal.addEventListener('close',()=>modal.remove());document.body.append(modal);modal.showModal();
    try{const jobs=(await sharedApi('jobs')).filter(row=>row.state==='completed');if(jobs.length){action('Load latest completed',()=>{location.href='/simulator/'+jobs[0].id;});for(const job of jobs){const b=document.createElement('button');b.className='action';b.style.cssText='display:block;width:100%;margin:8px 0;text-align:left';b.textContent=job.mission_name+' · '+(job.finished_at||'');b.onclick=()=>{location.href='/simulator/'+job.id;};rows.append(b);}}else note.textContent='No completed schedules found.';action('Import an existing schedule',()=>window.open('/?loadSchedule=1','_blank','noopener'));}catch(error){note.textContent=error.message;}
  });
  button('Import / download TLE',()=>window.open('/?tleSources=1','_blank','noopener'));
  button('Replay with another TLE',async()=>{
    const modal=document.createElement('dialog');modal.style.cssText='background:#102033;color:#e5f4ff;border:1px solid #41657d;border-radius:10px;padding:20px;width:min(750px,95vw)';
    const title=document.createElement('h3');title.textContent='Replay assignments with a different TLE source';const note=document.createElement('p');note.textContent='Creates a separate analysis job with this schedule’s assignments and resource snapshots. This job remains unchanged. Newly calculated visibility may disagree with the assignments.';const select=document.createElement('select');select.setAttribute('aria-label','Replay TLE source');modal.append(title,note,select);
    const start=document.createElement('button');start.className='action';start.textContent='Create replay job';start.disabled=true;const close=document.createElement('button');close.className='action';close.textContent='Close';close.onclick=()=>modal.close();modal.append(start,close);modal.addEventListener('close',()=>modal.remove());document.body.append(modal);modal.showModal();
    try{const records=await sharedApi('tles');for(const row of records){const option=document.createElement('option');option.value=row.id;option.textContent=row.name+' · '+row.satellites+' satellites';select.append(option);}start.disabled=!records.length;if(!records.length)note.textContent='Import or download a TLE source first.';}catch(error){note.textContent=error.message;}
    start.onclick=async()=>{start.disabled=true;try{const created=await sharedApi(`jobs/${cfg.job_id}/replay`,{tle_id:select.value,revision:cfg.revision});note.textContent='Replay queued. It will appear in the scheduler’s job history.';const poll=async()=>{if(!modal.open)return;try{const status=await sharedApi('jobs/'+created.id);if(status.state==='completed'){note.textContent='Replay ready. ';const link=document.createElement('a');link.href='/simulator/'+created.id;link.textContent='Open replay simulator';link.style.color='#75dbff';note.append(link);}else if(['failed','cancelled','interrupted'].includes(status.state)){note.textContent=status.message||'Replay did not complete.';}else{note.textContent='Replay '+status.state+'… Closing this window does not cancel the job.';setTimeout(poll,2000);}}catch(error){note.textContent=error.message;}};poll();}catch(error){note.textContent=error.message;start.disabled=false;}};
  });
  button('Monitoring pins',async()=>{
    const modal=document.createElement('dialog');modal.style.cssText='background:#102033;color:#e5f4ff;border:1px solid #41657d;border-radius:10px;padding:20px;max-width:700px;width:90vw;max-height:90vh;overflow:auto';
    const heading=document.createElement('h3');heading.textContent='Monitoring locations';const note=document.createElement('p');note.textContent='Pins apply to this browser/job. Saved monitoring locations are shared by everyone using this server.';modal.append(heading,note);
    const picker=document.createElement('select');picker.setAttribute('aria-label','Saved mission location');for(const name of Object.keys(cfg.locations).sort()){const option=document.createElement('option');option.value=name;option.textContent=name;picker.append(option);}modal.append(picker);
    const rows=document.createElement('div'),sharedRows=document.createElement('div'),status=document.createElement('p');status.setAttribute('role','status');
    let library={records:{},revision:null},original=null;
    function sync(){setPinnedLocations(pins.map((p,i)=>({...p,id:'pin-'+i,saved:p.saved===true})));lastKey='';persist();update();}
    function addPin(value){if(pins.length>=10){status.textContent='Maximum 10 monitoring pins.';return;}pins.push(value);refresh();sync();}
    function refresh(){rows.replaceChildren();pins.forEach((pin,index)=>{const row=document.createElement('p');row.textContent=pin.name+' ';const remove=document.createElement('button');remove.className='action';remove.textContent='Remove pin';remove.onclick=()=>{pins.splice(index,1);refresh();sync();};row.append(remove);rows.append(row);});}
    function action(parent,label,fn){const b=document.createElement('button');b.type='button';b.className='action';b.textContent=label;b.onclick=fn;parent.append(b);return b;}
    action(modal,'Pin selected mission location',()=>addPin({name:picker.value,...cfg.locations[picker.value],saved:true}));
    const form=document.createElement('form');const fields={};
    for(const [key,label,type]of [['name','Location name','text'],['latitude','Latitude','number'],['longitude','Longitude','number'],['elevation','Elevation (m)','number']]){const lab=document.createElement('label');lab.textContent=label;lab.style.display='block';const input=document.createElement('input');input.type=type;input.required=true;if(type==='number'){input.step='any';input.value='0';}if(key==='latitude'){input.min=-90;input.max=90;}if(key==='longitude'){input.min=-180;input.max=180;}if(key==='name')input.maxLength=100;lab.append(input);form.append(lab);fields[key]=input;}
    const saveLabel=document.createElement('label');saveLabel.style.display='block';const remember=document.createElement('input');remember.type='checkbox';saveLabel.append(remember,document.createTextNode('Save in shared monitoring library'));form.append(saveLabel);
    const submit=document.createElement('button');submit.className='action';submit.textContent='Add coordinates / save';form.append(submit);
    function clearEditor(){original=null;remember.checked=false;fields.name.value='';fields.latitude.value=0;fields.longitude.value=0;fields.elevation.value=0;}
    form.onsubmit=async event=>{event.preventDefault();const name=fields.name.value.trim(),value={latitude:Number(fields.latitude.value),longitude:Number(fields.longitude.value),elevation:Number(fields.elevation.value)};submit.disabled=true;try{if(!name)throw Error('Enter a location name.');if(remember.checked){library=await sharedApi('monitoring-locations',{action:'save',revision:library.revision,original,name,location:value});renderLibrary();status.textContent='Shared monitoring location saved.';}addPin({name,...value,saved:remember.checked});clearEditor();}catch(error){status.textContent=error.message;}finally{submit.disabled=false;}};
    action(form,'Cancel edit',clearEditor);modal.append(form,rows);const sharedHeading=document.createElement('h4');sharedHeading.textContent='Shared monitoring library';modal.append(sharedHeading,sharedRows,status);
    function renderLibrary(){sharedRows.replaceChildren();for(const [name,value]of Object.entries(library.records).sort(([a],[b])=>a.localeCompare(b))){const row=document.createElement('p');row.textContent=name+' ';action(row,'Pin',()=>addPin({name,...value,saved:true}));action(row,'Edit',()=>{original=name;remember.checked=true;for(const key of ['name','latitude','longitude','elevation'])fields[key].value=key==='name'?name:value[key];});action(row,'Delete saved',async()=>{if(!confirm('Delete '+name+' from the shared monitoring library? Existing selected pins keep their coordinates.'))return;try{library=await sharedApi('monitoring-locations',{action:'delete',revision:library.revision,original:name});renderLibrary();if(original===name)clearEditor();}catch(error){status.textContent=error.message;}});sharedRows.append(row);}if(!Object.keys(library.records).length)sharedRows.textContent='No saved monitoring locations yet.';}
    action(modal,'Close',()=>modal.close());modal.addEventListener('close',()=>modal.remove());document.body.append(modal);refresh();modal.showModal();try{library=await sharedApi('monitoring-locations');renderLibrary();}catch(error){status.textContent=error.message;}
  });
  document.querySelector('header').after(tools);
  setSatelliteMetadata(cfg.metadata);setStation(cfg.station);setLandingSite(cfg.mission_site);loadSchedule(cfg.schedule);
  try{const stored=JSON.parse(localStorage.getItem(storageKey)||'{}');if(Array.isArray(stored.pins))pins=stored.pins.slice(0,10);if(stored.dashboard)restoreDashboardState(stored.dashboard);}catch{}
  setPinnedLocations(pins.map((p,i)=>({...p,id:'pin-'+i,saved:p.saved===true})));
  setSpeed(document.getElementById('speedSelect').value);
  window.simulatorTransport={
    packet,
    async render(ms,paths=true){
      const deadline=performance.now()+40000;
      while(inFlight||navigating){if(performance.now()>deadline)throw Error('Wait for the current simulation request to finish.');await new Promise(resolve=>setTimeout(resolve,50));}
      let data;
      for(let attempt=0;attempt<30;attempt++){
        try{data=await call('frame',{...packet(),time:new Date(ms).toISOString(),paths});break;}
        catch(error){if(error.status!==429||attempt===29)throw error;await new Promise(resolve=>setTimeout(resolve,200));}
      }
      setVideoExportTime(ms);setOrbitData(data.results);if(data.paths)setOrbitPaths(data.paths);
      return data;
    },
    refresh(){lastKey='';lastPathKey=null;update();}
  };
  window.qtBridgeRequestOrbitUpdate=()=>update();
  window.addEventListener('pagehide',persist);
  setInterval(()=>{update();},500);
  setInterval(persist,10000);
  await update();
})();
