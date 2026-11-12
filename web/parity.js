/* Desktop-style mission controls and browser-local workspace preferences. */
'use strict';
(() => {
  const minuteInputs={};
  for(const direction of ['before','after']){
    const hours=$(direction);hours.step='1';const caption=document.querySelector(`label[for="${direction}"]`);caption.textContent=direction==='before'?'Before event':'After event';caption.classList.add('duration-caption');hours.setAttribute('aria-label',direction+' hours');
    const row=element('div');row.className='duration-inputs';hours.before(row);row.append(hours);
    const minutes=document.createElement('input');minutes.type='number';minutes.min=0;minutes.max=59;minutes.step=1;minutes.value=0;minutes.setAttribute('aria-label',direction+' minutes');row.append(minutes);for(const [input,title]of [[hours,'Hours'],[minutes,'Minutes']]){const field=element('div');field.className='duration-field';const unit=element('span',title);unit.className='duration-unit';field.append(unit,input);row.append(field);}minuteInputs[direction]=minutes;
  }
  const durationStyle=element('style');durationStyle.textContent='.duration-caption{white-space:nowrap;line-height:22px;min-height:22px}.duration-field{display:flex;flex-direction:column;gap:5px;min-width:0}.duration-unit{font-size:12px;line-height:18px;white-space:nowrap}.duration-inputs{align-items:start}';document.head.append(durationStyle);
  window.durationHours=direction=>Number($(direction).value)+Number(minuteInputs[direction].value)/60;
  window.setDurationHours=(direction,value)=>{const minutes=Math.round(Number(value)*60);$(direction).value=Math.floor(minutes/60);minuteInputs[direction].value=minutes%60;};
  windowHint=()=>{const when=new Date($('event').value.replace(' ','T')+'Z');if(!Number.isFinite(when.getTime()))return;const before=window.durationHours('before'),after=window.durationHours('after');$('window').textContent=`${new Date(when-before*3600000).toISOString().replace('T',' ').slice(0,19)} → ${new Date(when.getTime()+after*3600000).toISOString().replace('T',' ').slice(0,19)} UTC · ${Math.round((before+after)*60)} minutes`;};
  for(const node of [minuteInputs.before,minuteInputs.after,$('before'),$('after'),$('event')])node.addEventListener('input',()=>windowHint());
  const presetBox=element('details');presetBox.className='card';presetBox.append(element('summary','Mission presets & workspace'));const presetSelect=document.createElement('select');presetSelect.setAttribute('aria-label','Saved mission preset');presetBox.append(presetSelect);$('mission').parentNode.insertBefore(presetBox,$('mission'));
  let presetRows=[];
  function button(parent,title,action){const b=element('button',title);b.type='button';b.onclick=action;parent.append(b);return b;}
  function capture(){const strategy=window.getCoverageStrategy();if(!strategy.enabled)strategy.locations=[];return {mission_name:$('name').value,event_type:$('type').value,event_time:$('event').value.replace(' ','T')+'Z',hours_before:durationHours('before'),hours_after:durationHours('after'),ground_station:$('station').value,mission_location:$('site').value,tle_id:$('tle').value,satellites:chosen('satellites'),antennas:chosen('antennas'),scheduling_strategy:strategy};}
  function apply(data){for(const [id,key]of [['name','mission_name'],['type','event_type'],['station','ground_station'],['site','mission_location'],['tle','tle_id']])$(id).value=data[key]??'';if(data.event_time)$('event').value=new Date(data.event_time).toISOString().slice(0,19).replace('T',' ');for(const kind of ['before','after'])setDurationHours(kind,data['hours_'+kind]||0);for(const kind of ['satellites','antennas'])for(const box of $(kind).querySelectorAll('input'))box.checked=!box.disabled&&(data[kind]||[]).includes(box.value);window.dispatchEvent(new CustomEvent('restoreStrategy',{detail:data.scheduling_strategy||{}}));windowHint();}
  window.captureMissionFields=capture;window.applyMissionFields=apply;
  async function refreshPresets(){try{presetRows=await api('presets');presetSelect.replaceChildren();for(const preset of presetRows){const option=element('option',`${preset.mission.mission_name} · ${preset.saved_at.slice(0,10)}`);option.value=preset.id;presetSelect.append(option);}}catch(error){message(error.message,true);}}
  button(presetBox,'Save mission preset',async()=>{try{await api('presets',capture());await refreshPresets();message('Mission preset saved on the server.');}catch(error){message(error.message,true);}});
  button(presetBox,'Load preset',()=>{const row=presetRows.find(p=>p.id===presetSelect.value);if(row){apply(row.mission);message('Preset loaded. Review UTC event time, libraries and TLE availability.');}});
  button(presetBox,'Archive preset',async()=>{const row=presetRows.find(p=>p.id===presetSelect.value);if(row&&confirm('Archive this saved preset?')){try{await api(`presets/${row.id}/archive`,{});await refreshPresets();}catch(error){message(error.message,true);}}});
  button(presetBox,'Reset workspace controls',()=>{if(!confirm('Reset mission fields and browser layout? Server libraries and saved schedules are unchanged.'))return;try{localStorage.removeItem('meosar-workspace');localStorage.removeItem('meosar-layout');}catch{}apply({mission_name:'',event_type:'Landing',event_time:new Date().toISOString(),hours_before:1,hours_after:3,ground_station:'Goddard',mission_location:'',tle_id:'auto',satellites:Object.entries(window.serverLibraries?.satellites||{}).filter(([,s])=>s.enabled).map(([n])=>n),antennas:Object.entries(window.serverLibraries?.antennas||{}).filter(([,a])=>a.operational).map(([n])=>n)});window.resetWorkspaceLayout();});
  const autoButton=button($('tle').parentElement,'Review automatic TLE selection',async()=>{try{const result=await api('tles/automatic',{satellites:chosen('satellites'),event_time:$('event').value.replace(' ','T')+'Z'});await resources();$('tle').value=result.id;message(`Nearest-epoch selection prepared for ${result.available_norad_ids.length} satellites. Missing: ${result.missing_norad_ids.join(', ')||'none'}. Maximum epoch difference: ${result.maximum_epoch_difference_hours.toFixed(1)} hours.`);}catch(error){message(error.message,true);}});
  $('tle').after(autoButton);
  let layout={outputs:false,details:{}};
  try{layout=JSON.parse(localStorage.getItem('meosar-layout')||'null')||layout;}catch{}
  layout.details={...(layout.details||{}),'Satellite selection':true,'Antenna selection':true};
  function saveLayout(){try{localStorage.setItem('meosar-layout',JSON.stringify(layout));}catch{}}
  function detailKey(node){return node.id||node.querySelector('summary')?.textContent.trim();}
  function applyLayout(){for(const node of document.querySelectorAll('details')){if(node.closest('dialog')||node.closest('#graphs')||node.id==='previousJobs')continue;const key=detailKey(node);if(typeof layout.details?.[key]==='boolean')node.open=layout.details[key];}}
  document.addEventListener('toggle',event=>{const node=event.target;if(node.tagName!=='DETAILS'||node.closest('dialog'))return;const key=detailKey(node);if(key){layout.details=layout.details||{};layout.details[key]=node.open;saveLayout();}},true);
  for(const event of ['jobRendered','resourcesReady'])window.addEventListener(event,()=>setTimeout(applyLayout,0));
  const outputs=button(document.querySelector('header'),'Outputs only',()=>{document.body.classList.toggle('outputs-only');outputs.textContent=document.body.classList.contains('outputs-only')?'Show mission inputs':'Outputs only';layout.outputs=document.body.classList.contains('outputs-only');saveLayout();});outputs.style.width='auto';document.body.classList.toggle('outputs-only',!!layout.outputs);outputs.textContent=layout.outputs?'Show mission inputs':'Outputs only';applyLayout();
  window.resetWorkspaceLayout=()=>{layout={outputs:false,details:{}};document.body.classList.remove('outputs-only');outputs.textContent='Outputs only';for(const detail of document.querySelectorAll('main details')){if(detail.closest('dialog'))continue;detail.open=detail.contains($('antennas'))||detail.contains($('satellites'));const key=detailKey(detail);if(key)layout.details[key]=detail.open;}saveLayout();};
  const css=document.createElement('style');css.textContent='.outputs-only main>aside{display:none}.outputs-only main{grid-template-columns:minmax(0,1fr)}';document.head.append(css);
  const freshness=element('p','No saved result selected.');freshness.style.fontSize='12px';$('mission').append(freshness);let completedInputs=null;
  window.addEventListener('jobRendered',async event=>{try{completedInputs=await api(`jobs/${event.detail.id}/inputs`);}catch{completedInputs=null;}});
  function fingerprint(data){const copy={...data};copy.satellites=[...(copy.satellites||[])].sort();copy.antennas=[...(copy.antennas||[])].sort();if(copy.event_time)copy.event_time=new Date(copy.event_time).toISOString();return JSON.stringify(copy);}
  let restorePending=true;
  window.addEventListener('resourcesReady',()=>{if(!restorePending)return;restorePending=false;try{const saved=JSON.parse(localStorage.getItem('meosar-workspace')||'null');if(saved)apply(saved);}catch{}});
  if(window.serverLibraries){window.dispatchEvent(new CustomEvent('resourcesReady',{detail:window.serverLibraries}));}
  setInterval(()=>{try{const data=capture();localStorage.setItem('meosar-workspace',JSON.stringify(data));const shape=completedInputs&&Object.fromEntries(Object.keys(data).map(k=>[k,completedInputs[k]]));freshness.textContent=!shape?'Generate or select a completed schedule.':fingerprint(data)===fingerprint(shape)?'Fields match the selected run. Library changes still require regeneration.':'Inputs differ from the selected result. Generate again to apply them.';}catch{}},1500);
  const previewBox=document.createElement('details');previewBox.className='spacer';previewBox.append(element('summary','Simulator preview · expand to load'));
  const previewInfo=element('p','Preview uses the selected completed job. Collapse to release its browser resources.');previewBox.append(previewInfo);const openPreview=button(previewBox,'Open active schedule in simulator',()=>{if(previewJob)window.open('/simulator/'+previewJob+'?revision='+encodeURIComponent(previewRevision),'_blank','noopener');});openPreview.disabled=true;
  const previewArea=element('div');previewBox.append(previewArea);$('timelineMount').parentNode.append(previewBox);
  let previewJob=null,previewRevision='original',previewRequest=0;
  async function loadPreview(){const request=++previewRequest;if(!previewBox.open||!selectedJob){previewArea.replaceChildren();previewJob=null;openPreview.disabled=true;return;}const job=selectedJob;try{const editor=await api(`jobs/${job}/editor`);if(request!==previewRequest||job!==selectedJob||!previewBox.open)return;const revision=editor.revision;if(previewJob===job&&previewRevision===revision)return;previewJob=job;previewRevision=revision;openPreview.disabled=false;const frame=document.createElement('iframe');frame.title='Embedded mission simulator';frame.src='/simulator/'+job+'?embed=1&revision='+encodeURIComponent(revision);frame.style.cssText='width:100%;height:clamp(320px,55vh,650px);border:1px solid #36516d;border-radius:8px';previewArea.replaceChildren(frame);previewInfo.textContent='Active saved schedule · '+(revision==='original'?'original calculation':'edited revision')+'.';}catch(error){if(request===previewRequest){previewJob=null;openPreview.disabled=true;previewInfo.textContent=error.message;}}}
  previewBox.addEventListener('toggle',loadPreview);window.addEventListener('jobRendered',loadPreview);window.addEventListener('workspaceReset',()=>{previewRequest++;previewJob=null;openPreview.disabled=true;previewArea.replaceChildren();previewInfo.textContent='Generate or select a completed mission to preview.';});
  window.addEventListener('presetsChanged',refreshPresets);windowHint();refreshPresets();
})();

/* Existing schedule-file loading, with explicit antenna identity mapping. */
(() => {
  const launch=element('button','Load existing mission');launch.type='button';$('manageLibraries').parentElement.append(launch);
  launch.onclick=()=>window.openSimulatorUpload('scheduler');
})();

/* Open a requested data dialog when coming from the simulator toolbar. */
(() => {
  const query=new URLSearchParams(location.search);
  const caption=query.get('tleSources')==='1'?'TLE sources & folders':query.get('loadSchedule')==='1'?'Load existing mission':null;
  if(!caption)return;
  function open(){const control=[...document.querySelectorAll('button')].find(button=>button.textContent===caption);if(control)control.click();}
  if(window.serverLibraries)setTimeout(open,0);
  else window.addEventListener('resourcesReady',open,{once:true});
})();
