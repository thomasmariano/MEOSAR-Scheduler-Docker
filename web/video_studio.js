/* Deterministic compositor frames in-browser; bounded FFmpeg encoding in Docker. */
'use strict';
(() => {
  const cfg=simulatorConfig;let activeId=null;
  const launch=document.createElement('button');launch.className='action';launch.textContent='Video Studio';(document.getElementById('simulatorExportActions')||document.querySelector('header').nextElementSibling).append(launch);
  async function apiVideo(path,body){const response=await fetch('/api/'+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json','X-MEOSAR-Request':'1'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Error(data.detail||'Video request failed.');return data;}
  const prefix=`jobs/${cfg.job_id}/videos`;
  window.addEventListener('pagehide',()=>{if(activeId)fetch(`/api/${prefix}/${activeId}/cancel`,{method:'POST',headers:{'Content-Type':'application/json','X-MEOSAR-Request':'1'},body:'{}',keepalive:true}).catch(()=>{});});
  launch.onclick=async()=>{
    pauseVideoDialog();const origin=simTimeMs;
    const modal=document.createElement('dialog');modal.style.cssText='background:#102033;color:#e0efff;border:1px solid #426680;border-radius:12px;padding:20px;width:min(1100px,96vw);max-height:92vh;overflow:auto';
    const title=document.createElement('h2');title.textContent='Video Studio';modal.append(title);
    const info=document.createElement('p');info.textContent='The browser renders the globe; Docker encodes the video. Keep this tab open until export finishes. Scene size is preserved and panel margins are fixed for the entire clip.';modal.append(info);
    const grid=document.createElement('div');grid.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px';modal.append(grid);
    function field(label,type,value){const lab=document.createElement('label');lab.textContent=label;lab.style.display='block';const input=document.createElement('input');input.type=type;input.value=value;input.setAttribute('aria-label',label);input.style.cssText='display:block;width:100%;box-sizing:border-box;padding:8px';lab.append(input);grid.append(lab);return input;}
    function select(label,rows,value){const lab=document.createElement('label');lab.textContent=label;const node=document.createElement('select');node.style.cssText='display:block;width:100%;padding:8px';node.setAttribute('aria-label',label);for(const [id,text]of rows){const option=document.createElement('option');option.value=id;option.textContent=text;node.append(option);}node.value=value;lab.append(node);grid.append(lab);return node;}
    const first=field('Start UTC','datetime-local',new Date(schedule.startMs).toISOString().slice(0,19));first.step='1';
    const last=field('End UTC','datetime-local',new Date(schedule.endMs).toISOString().slice(0,19));last.step='1';
    const seconds=field('Video duration (seconds)','number','60');seconds.min=.1;seconds.max=600;seconds.step='any';
    const rate=field('Playback speed (×)','number',((schedule.endMs-schedule.startMs)/60000).toFixed(2));rate.min='.01';rate.step='any';
    const resolution=select('Globe resolution',[['640x360','640 × 360'],['854x480','854 × 480'],['1280x720','1280 × 720'],['1920x1080','1920 × 1080'],['2560x1440','2560 × 1440'],['3840x2160','3840 × 2160 (4K)']],'1280x720');
    const fps=select('Frames per second',[['10','10 FPS'],['12','12 FPS'],['15','15 FPS'],['24','24 FPS'],['30','30 FPS']],'24');
    const format=select('Video format',[['mp4','MP4 (H.264)'],['webm','WebM (VP9)']],'mp4');
    const quality=select('File size / quality',[['small','Small file'],['balanced','Balanced'],['high','High quality']],'balanced');
    const camera=select('Camera',[['auto','Automatically position'],['current','Use current camera']],'auto');
    const globeStyle=select('Globe layers',[['current','Globe with current layers'],['clean','Clean globe and satellites']],'current');
    const mode=select('Layout preset',[['full','Full dashboard'],['minimal','Timeline and key'],['caption','Globe + compact mission caption'],['globe','Globe only']],'full');
    const options=document.createElement('div');options.style.cssText='display:flex;flex-wrap:wrap;gap:12px;margin:15px 0';modal.append(options);const panels={};
    for(const [key,label]of [['missionInfo','Mission information'],['compactInfo','Compact mission box'],['legend','Color key'],['coverage','Location coverage'],['assignments','Active contacts'],['timeline','UTC timeline'],['stamp','UTC timestamp']]){const lab=document.createElement('label');lab.style.cssText='display:flex;align-items:center;gap:5px';const input=document.createElement('input');input.type='checkbox';panels[key]=input;lab.append(input,document.createTextNode(label));options.append(lab);}
    function preset(){const full=mode.value==='full',minimal=mode.value==='minimal',caption=mode.value==='caption';for(const [key,input]of Object.entries(panels))input.checked=key==='missionInfo'?(full||caption):key==='compactInfo'?caption:key==='legend'?(full||minimal):key==='timeline'?(full||minimal):key==='stamp'?false:full;}
    preset();
    const estimate=document.createElement('p'),progress=document.createElement('progress'),status=document.createElement('p');progress.max=1;progress.value=0;progress.style.width='100%';status.setAttribute('role','status');status.style.whiteSpace='pre-wrap';modal.append(estimate,progress,status);
    const preview=document.createElement('img');preview.alt='Still video preview';preview.style.cssText='display:none;width:100%;max-height:480px;object-fit:contain;background:#030810';modal.append(preview);
    const liveLabel=document.createElement('label'),live=document.createElement('input');live.type='checkbox';liveLabel.style.cssText='display:flex;gap:8px;align-items:center;margin:12px 0';liveLabel.append(live,document.createTextNode('Live preview — selected range and speed (stop to change settings)'));modal.append(liveLabel);
    const buttons=document.createElement('div');buttons.style.cssText='display:flex;gap:10px;flex-wrap:wrap;margin:14px 0';modal.append(buttons);
    function button(label,fn){const b=document.createElement('button');b.className='action';b.textContent=label;b.onclick=fn;buttons.append(b);return b;}
    let pickingCamera=false;let busy=false,phase=null,cancelled=false,previewSecondsPerFrame=null,capable=false;
    let maxSeconds=600,maxFrames=18000,liveActive=false,livePromise=null,liveToken=0;
    function times(){const a=Date.parse(first.value.replace(' ','T')+'Z'),b=Date.parse(last.value.replace(' ','T')+'Z');if(!Number.isFinite(a)||!Number.isFinite(b)||a<schedule.startMs||b>schedule.endMs||b<=a)throw Error('Choose a valid UTC interval within this schedule.');return [a,b];}
    function settings(){const [a,b]=times(),duration=Number(seconds.value),n=Math.max(2,Math.ceil(duration*Number(fps.value)));if(!Number.isFinite(duration)||duration<.1||duration>maxSeconds||n>maxFrames)throw Error(`Use a 0.1–${maxSeconds} second clip with at most ${maxFrames.toLocaleString()} frames. Reduce duration or FPS.`);const [width,height]=resolution.value.split('x').map(Number);const factor=quality.value==='small'?.6:quality.value==='high'?1.8:1;const kbps=Math.min(30000,Math.max(300,Math.round(2500*(height/720)**1.6*factor)));const sidebar={mode:mode.value,first:a,last:b,speed:(b-a)/1000/(n/Number(fps.value))};for(const [key,input]of Object.entries(panels))if(key!=='stamp')sidebar[key]=input.checked;return {a,b,width,height,n,fps:Number(fps.value),kbps,sidebar,duration:n/Number(fps.value)};}
    function durationText(value){const sec=Math.ceil(value);return `${Math.floor(sec/60)}m ${String(sec%60).padStart(2,'0')}s`;}
    function estimates(){try{const s=settings();const mb=s.kbps*1000/8*s.duration/1024/1024;estimate.textContent=`Video: ${durationText(s.duration)} · ${s.sidebar.speed.toFixed(2)}× · ${s.n} frames · estimated file ${mb.toFixed(1)} MiB (content-dependent). ${previewSecondsPerFrame?`Estimated render: ${durationText(previewSecondsPerFrame*s.n*2)} plus encoding.`:'Create a still preview to estimate render time.'} Panels may extend the canvas without shrinking the globe.`;exportButton.disabled=busy||!capable;}catch(e){estimate.textContent=e.message;exportButton.disabled=true;}}
    function dirty(){preview.style.display='none';status.textContent='Settings changed. Refresh the still preview.';estimates();}
    function updateSpeed(){try{const [a,b]=times();rate.value=((b-a)/1000/Number(seconds.value)).toFixed(2);}catch{}dirty();}
    seconds.oninput=updateSpeed;first.oninput=updateSpeed;last.oninput=updateSpeed;rate.oninput=()=>{try{const [a,b]=times();seconds.value=((b-a)/1000/Number(rate.value)).toFixed(2);}catch{}dirty();};
    mode.onchange=()=>{preset();dirty();};for(const node of [resolution,fps,format,quality,camera,globeStyle,...Object.values(panels)])node.addEventListener('change',dirty);
    function lock(value,kind=null){busy=value;phase=value?kind:null;for(const node of [...grid.querySelectorAll('input,select'),...Object.values(panels)])node.disabled=value;live.disabled=value&&kind!=='live';previewButton.disabled=value;closeButton.disabled=value&&kind!=='live';cancelButton.disabled=!value;exportButton.disabled=value||!capable;}
    function checkCancel(){if(cancelled)throw Error('Export cancelled.');}
    async function render(ms,paths){checkCancel();await window.simulatorTransport.render(ms,paths);checkCancel();}
    function capture(s,ms,extra){const image=captureVideoFrame(s.width,s.height,ms,panels.stamp.checked,{...s.sidebar,...extra});if(image.error)throw Error(image.error);return image;}
    function begin(){window.meosarVideoBusy=true;beginVideoExport(camera.value==='auto',globeStyle.value==='clean');document.body.style.pointerEvents='';}
    function restore(){finishVideoExport();window.meosarVideoBusy=false;window.simulatorTransport.refresh();}
    const previewButton=button('Refresh still preview',async()=>{if(busy)return;cancelled=false;lock(true,'still');const started=performance.now();try{const s=settings(),ms=Math.max(s.a,Math.min(s.b,origin));begin();await render(ms,showGroundTracks||showOrbitPaths);const measured=capture(s,ms,{preflight:true});const image=capture(s,ms,{lockedMargins:measured.margins});preview.src='data:image/png;base64,'+image.png;preview.style.display='block';previewSecondsPerFrame=(performance.now()-started)/1000;status.textContent=`Still preview at ${new Date(ms).toISOString()} · ${image.width} × ${image.height}. Export scans the complete clip and may add fixed margins to protect later satellite positions.`;}catch(e){status.textContent=e.message;}finally{restore();lock(false);estimates();}});
    const exportButton=button('Export video',async()=>{if(busy)return;cancelled=false;lock(true,'export');let id=null;const started=performance.now();try{const s=settings();begin();let margins={left:0,right:0,bottom:0};let pathKey=null;for(let index=0;index<s.n;index++){const ms=Math.round(s.a+(s.b-s.a)*index/(s.n-1));const key=Math.floor(ms/300000);await render(ms,(showGroundTracks||showOrbitPaths)&&key!==pathKey);pathKey=key;const frame=capture(s,ms,{preflight:true});for(const side of ['left','right','bottom'])margins[side]=Math.max(margins[side],frame.margins[side]||0);progress.value=index/s.n*.5;status.textContent=`Checking fixed panel layout: ${index+1}/${s.n} frames. Elapsed ${durationText((performance.now()-started)/1000)}.`;}
      await render(s.a,showGroundTracks||showOrbitPaths);const firstFrame=capture(s,s.a,{lockedMargins:margins});const exportState=await apiVideo(prefix,{revision:cfg.revision,first:s.a,last:s.b,fps:s.fps,frames:s.n,width:firstFrame.width,height:firstFrame.height,format:format.value,kbps:s.kbps});id=exportState.id;activeId=id;pathKey=null;
      for(let index=0;index<s.n;index++){const ms=Math.round(s.a+(s.b-s.a)*index/(s.n-1));const key=Math.floor(ms/300000);await render(ms,(showGroundTracks||showOrbitPaths)&&key!==pathKey);pathKey=key;const image=capture(s,ms,{lockedMargins:margins});checkCancel();const bytes=Uint8Array.from(atob(image.png),char=>char.charCodeAt(0));const response=await fetch(`/api/${prefix}/${id}/frames/${index}`,{method:'POST',headers:{'Content-Type':'image/png','X-MEOSAR-Request':'1','X-Simulation-Time-Ms':String(ms)},body:bytes});if(!response.ok){const error=await response.json();throw Error(error.detail||'Frame upload failed.');}progress.value=.5+(index+1)/s.n*.5;const elapsed=(performance.now()-started)/1000;status.textContent=`Rendering and encoding: ${index+1}/${s.n} frames. Elapsed ${durationText(elapsed)}.`;}
      checkCancel();status.textContent='Finalizing video…';const done=await apiVideo(`${prefix}/${id}/finish`,{});if(done.state!=='completed')throw Error(done.message||'Encoding did not complete.');activeId=null;id=null;progress.value=1;const link=document.createElement('a');link.href=`/api/${prefix}/${done.id}/download`;link.textContent=`Download ${format.value.toUpperCase()} · ${(done.bytes/1024/1024).toFixed(1)} MiB`;link.style.color='#76daff';status.replaceChildren(document.createTextNode('Export complete. '),link);await history();
    }catch(e){status.textContent=e.message;if(id)await apiVideo(`${prefix}/${id}/cancel`,{}).catch(()=>{});}finally{activeId=null;restore();lock(false);estimates();}});
    exportButton.disabled=true;
    const cancelButton=button('Stop preview / cancel export',()=>{if(phase==='live'){live.checked=false;stopLive();return;}cancelled=true;status.textContent='Cancelling…';if(activeId)apiVideo(`${prefix}/${activeId}/cancel`,{}).catch(()=>{});});cancelButton.disabled=true;
    const closeButton=button('Close',async()=>{await stopLive();modal.close();});
    async function stopLive(){
      if(!liveActive){if(phase==='live'&&livePromise)await livePromise;return;}
      liveActive=false;++liveToken;live.checked=false;status.textContent='Stopping live preview…';
      if(livePromise)await livePromise;
    }
    function startLive(){
      if(busy){live.checked=false;return;}
      cancelled=false;liveActive=true;const token=++liveToken;lock(true,'live');
      livePromise=(async()=>{
        try{
          const s=settings();begin();const startClock=performance.now();let pathKey=null;
          while(liveActive&&token===liveToken&&modal.open){
            const started=performance.now();
            const elapsed=(started-startClock)*s.sidebar.speed;
            const ms=Math.round(s.a+elapsed%(s.b-s.a));
            const key=Math.floor(ms/300000);
            await render(ms,(showGroundTracks||showOrbitPaths)&&key!==pathKey);pathKey=key;
            if(!liveActive||token!==liveToken||!modal.open)break;
            const image=capture(s,ms,{fixedPreview:true});
            preview.src='data:image/png;base64,'+image.png;preview.style.display='block';
            const cost=(performance.now()-started)/1000;
            previewSecondsPerFrame=previewSecondsPerFrame===null?cost:previewSecondsPerFrame*.8+cost*.2;
            status.textContent=`Live preview · ${new Date(ms).toISOString()} · ${s.sidebar.speed.toFixed(2)}×. Preview uses fixed gutters; export determines final margins across all frames.`;
            await new Promise(resolve=>setTimeout(resolve,400));
          }
        }catch(error){status.textContent=error.message;}
        finally{liveActive=false;live.checked=false;restore();lock(false);estimates();}
      })();
    }
    live.onchange=()=>{if(live.checked)startLive();else stopLive();};
    const library=document.createElement('div');modal.append(library);
    async function history(){try{const rows=await apiVideo(prefix);library.replaceChildren();const heading=document.createElement('h3');heading.textContent='Saved videos for this job';library.append(heading);for(const row of rows){if(row.state!=='completed')continue;const p=document.createElement('p'),link=document.createElement('a');link.href=`/api/${prefix}/${row.id}/download`;link.style.color='#76daff';link.textContent=`${row.settings.format.toUpperCase()} · ${new Date(row.created_at).toISOString().replace('T',' ').slice(0,19)+' UTC'} · ${(row.bytes/1024/1024).toFixed(1)} MiB · ${row.settings.revision==='original'?'Original':'Edited revision'}`;p.append(link);library.append(p);}}catch{}}
    const angleButton=button('Set camera angle',async()=>{
      await stopLive();if(busy)return;
      pickingCamera=true;modal.close();
      const old=[globeYaw,globePitch,globeZoom],panel=document.createElement('div');panel.className='camera-angle-panel';
      panel.style.cssText='position:fixed;top:12px;left:12px;z-index:10000;background:#101e30;color:white;padding:16px;border:1px solid #789;border-radius:10px;max-width:320px';
      const caption=document.createElement('p');caption.textContent='Drag the globe to choose your angle, or enter exact values.';panel.append(caption);
      const fields=[];for(const [label,value,min,max]of [['Latitude',globePitch*180/Math.PI,-85,85],['Longitude',-globeYaw*180/Math.PI,-180,180],['Zoom',globeZoom,.35,3]]){const l=document.createElement('label');l.textContent=label;const input=document.createElement('input');input.type='number';input.value=value.toFixed(2);input.min=min;input.max=max;input.step='.01';l.append(input);panel.append(l);fields.push(input);input.oninput=()=>{const v=fields.map(f=>Number(f.value));if(v.every(Number.isFinite)){globePitch=Math.max(-85,Math.min(85,v[0]))*Math.PI/180;globeYaw=-Math.max(-180,Math.min(180,v[1]))*Math.PI/180;globeZoom=Math.max(.35,Math.min(3,v[2]));drawGlobe();}};}
      const timer=setInterval(()=>{[globePitch*180/Math.PI,-globeYaw*180/Math.PI,globeZoom].forEach((v,i)=>{if(document.activeElement!==fields[i])fields[i].value=v.toFixed(2);});},200);
      const actions=document.createElement('div');actions.className='camera-angle-actions';panel.append(actions);for(const [label,use]of [['Use this angle',true],['Cancel angle',false]]){const b=document.createElement('button');b.textContent=label;b.onclick=()=>{clearInterval(timer);panel.remove();if(!use){[globeYaw,globePitch,globeZoom]=old;drawGlobe();}else camera.value='current';pickingCamera=false;modal.showModal();dirty();};actions.append(b);}document.body.append(panel);
    });
    camera.parentElement.append(angleButton);
    modal.addEventListener('cancel',event=>{if(busy){event.preventDefault();if(phase==='live'){stopLive().then(()=>modal.close());}}});modal.addEventListener('close',()=>{if(pickingCamera)return;resumeVideoDialog();modal.remove();});document.body.append(modal);modal.showModal();
    try{const capability=await apiVideo('videos/capabilities');capable=capability.available;maxSeconds=capability.max_seconds;maxFrames=capability.max_frames;seconds.max=maxSeconds;if(!capable)status.textContent='FFmpeg is missing from the server. Rebuild the updated Docker image.';}catch(e){status.textContent=e.message;}estimates();history();
  };
})();
