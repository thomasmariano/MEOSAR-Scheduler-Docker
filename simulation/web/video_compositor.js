let videoFixedLayout = null;
let videoExportSnapshot = null;
let videoDialogPlaying = null;
let videoDialogResumePending = false;
function pauseVideoDialog() {
  if(videoDialogPlaying===null) videoDialogPlaying=playing;
  playing=false;lastFrame=0;
}
function resumeVideoDialog() {
  if(videoExportSnapshot) {videoDialogResumePending=true;return;}
  videoDialogResumePending=false;
  if(videoDialogPlaying!==null) playing=videoDialogPlaying;
  videoDialogPlaying=null;lastFrame=0;
}

function beginVideoExport(autoCamera, cleanView) {
  if(videoExportSnapshot) return;
  videoFixedLayout=null;
  videoExportSnapshot={playing,simTimeMs,globeYaw,globePitch,globeZoom,showCoverage,showGroundTracks,showOrbitPaths};
  playing=false;
  if(autoCamera) {
    const locations=coverageLocations(); let x=0,y=0,z=0;
    for(const p of locations) {const lat=p.latitude*Math.PI/180, lon=p.longitude*Math.PI/180;
      x+=Math.cos(lat)*Math.cos(lon);y+=Math.sin(lat);z+=Math.cos(lat)*Math.sin(lon);}
    if(Math.hypot(x,y,z)>0.01) {globeYaw=-Math.atan2(z,x);globePitch=Math.atan2(y,Math.hypot(x,z));}
    globeZoom=0.72;
  }
  if(cleanView) {showCoverage=false;showGroundTracks=false;showOrbitPaths=false;}
  // Prevent playback, scrubbing and camera changes from disturbing fixed-frame export.
  document.body.style.pointerEvents='none';
  drawGlobe();
}
function setVideoExportTime(ms) {simTimeMs=ms;playing=false;updateClock();renderSchedule();}
function captureVideoFrame(width,height,expected,stamp,sidebar={}) {
  if(dataTimeMs===null || Math.abs(dataTimeMs-expected)>2) return {error:'Orbit data timestamp does not match the requested export frame.'};
  drawGlobe();
  const baseWidth=width,baseHeight=height;
  const u=baseHeight/720,pad=14*u,font=14*u,line=21*u;
  const mode=sidebar.mode||'full',full=mode==='full',minimal=mode==='minimal';
  const dashboard=sidebar.timeline===undefined?(full||minimal):!!sidebar.timeline,footH=dashboard?70*u:0;
  const hasRight=!!(sidebar.coverage||sidebar.assignments);
  const sideW=hasRight?baseWidth*.29:0;
  const keyWidth=baseWidth*.26;
  const hasKey=!!sidebar.legend;
  const hasInfo=sidebar.missionInfo!==false;
  const compactInfo=!!sidebar.compactInfo;
  const infoFont=font*(compactInfo ? .76 : 1);
  const mission=schedule?.mission_info||{};
  const first=sidebar.first??schedule.startMs,last=sidebar.last??schedule.endMs;
  const stampTime=ms=>Number.isFinite(ms)?`${fmtDate(ms)} ${fmtTime(ms)}`:'Unavailable';
  const eventMs=Date.parse(mission.event_time||'');
  let fields=[
    ['MISSION',mission.name||'Title unavailable'],
    ['EVENT TYPE',mission.type||'Unavailable'],
    ['EVENT UTC',stampTime(eventMs)],
    ['VIDEO START',stampTime(first)],
    ['VIDEO END',stampTime(last)],
    ['GROUND STATION',station?.name||'Unavailable'],
    ['MISSION SITE',landingSite?.name||'Unavailable']
  ];
  if(compactInfo)fields=[
    ['MISSION',(mission.name||'Title unavailable')+' · '+(mission.type||'Type unavailable')],
    ['VIDEO UTC',stampTime(first)+' → '+stampTime(last)],
    ['EVENT UTC',stampTime(eventMs)],
    ['LOCATIONS',(station?.name||'Station unavailable')+' / '+(landingSite?.name||'Site unavailable')]
  ];
  if(pinnedLocations.length)fields.push(['MONITORED LOCATIONS',pinnedLocations.map(p=>p.name||p.id).join(', ')]);
  const measure=document.createElement('canvas').getContext('2d');measure.font=`${infoFont}px Arial`;
  function wrapInfo(value) {
    const lines=[];let current='';
    for(const char of String(value)) {
      if(char==='\n'){lines.push(current);current='';continue;}
      if(current && measure.measureText(current+char).width>keyWidth-2*pad){lines.push(current.trimEnd());current='';}
      current+=char;
    }
    if(current)lines.push(current.trim());return lines.length?lines:['Unavailable'];
  }
  const infoRows=hasInfo?fields.map(([label,value])=>({label,lines:wrapInfo(value)})):[];
  const infoHeight=hasInfo?line*1.7+infoRows.reduce((sum,row)=>sum+infoFont*.95+row.lines.length*infoFont*1.22+infoFont*.55,0)+pad*.5:0;
  const leftHeight=infoHeight+(hasKey?(hasInfo?pad:0)+line*6.7:0);

  // Protect the actual Earth disc and displayed satellite markers/labels,
  // not empty space in the whole canvas. Scene scale never depends on panels.
  const sceneScale=Math.min(baseWidth/canvas.width,baseHeight/canvas.height);
  const sceneX=(baseWidth-canvas.width*sceneScale)/2;
  const sceneY=(baseHeight-canvas.height*sceneScale)/2;
  const css=canvas.getBoundingClientRect();
  const sx=canvas.width/Math.max(1,css.width)*sceneScale;
  const sy=canvas.height/Math.max(1,css.height)*sceneScale;
  const globe={x:sceneX+css.width*.5*sx,y:sceneY+css.height*.51*sy,
    radius:Math.min(css.height*.40,css.width*.34,250)*globeZoom*Math.max(sx,sy)+10*u};
  const protectedSatellites=satelliteHits.map(hit=>({
    x:sceneX+(hit.x-12)*sx,y:sceneY+(hit.y-22)*sy,
    w:((hit.labelWidth||80)+34)*sx,h:42*sy
  }));
  const overlaps=(a,b)=>a.x<b.x+b.w && a.x+a.w>b.x && a.y<b.y+b.h && a.y+a.h>b.y;
  function coversImportant(rect) {
    const nearX=Math.max(rect.x,Math.min(globe.x,rect.x+rect.w));
    const nearY=Math.max(rect.y,Math.min(globe.y,rect.y+rect.h));
    if(Math.hypot(nearX-globe.x,nearY-globe.y)<globe.radius)return true;
    return protectedSatellites.some(bounds=>overlaps(rect,bounds));
  }
  const keyRect={x:pad,y:pad,w:keyWidth,h:leftHeight};
  const rightRect={x:baseWidth-sideW,y:0,w:sideW,h:baseHeight-footH};
  const bottomRect={x:0,y:baseHeight-footH,w:baseWidth,h:footH};
  const framePlan={
    left:leftHeight>0 && coversImportant(keyRect)?Math.ceil(keyWidth+2*pad):0,
    right:hasRight && coversImportant(rightRect)?Math.ceil(sideW):0,
    bottom:dashboard && coversImportant(bottomRect)?Math.ceil(footH):0
  };
  // The export scans all output timestamps first. This locked plan avoids
  // dimension changes or panel jumping later in the encoded clip.
  // Preflight only measures; never lock a layout from a scanned frame.
  if(sidebar.preflight)return {margins:framePlan,time:expected};
  // Live preview is a series of short export sessions: use fixed gutters,
  // independent of satellite positions, so every preview uses one layout.
  const previewMargins={left:leftHeight>0?Math.ceil(keyWidth+2*pad):0,
    right:hasRight?Math.ceil(sideW):0,bottom:dashboard?Math.ceil(footH):0};
  if(!videoFixedLayout) {
    const margins=sidebar.fixedPreview?previewMargins:sidebar.lockedMargins;
    if(!margins)return {error:'Export layout has not been locked by preflight.'};
    videoFixedLayout={left:Number(margins.left)||0,right:Number(margins.right)||0,
      bottom:Number(margins.bottom)||0};
  }
  const plan=videoFixedLayout;
  // Even pixel dimensions are required by the yuv420p encoding path.
  width=Math.ceil((baseWidth+plan.left+plan.right)/2)*2;
  if(plan.outputHeight===undefined)
    plan.outputHeight=Math.ceil(Math.max(baseHeight+plan.bottom,leftHeight+2*pad+plan.bottom)/2)*2;
  height=plan.outputHeight;
  const sideX=width-sideW;
  const image=document.createElement('canvas');image.width=width;image.height=height;
  const c=image.getContext('2d');c.fillStyle='#030810';c.fillRect(0,0,width,height);
  const scale=Math.min(baseWidth/canvas.width,baseHeight/canvas.height);
  const dx=plan.left+(baseWidth-canvas.width*scale)/2;
  const dy=(baseHeight-canvas.height*scale)/2;
  c.save();c.beginPath();c.rect(plan.left,0,baseWidth,baseHeight);c.clip();
  c.drawImage(canvas,dx,dy,canvas.width*scale,canvas.height*scale);c.restore();
  function text(value,x,y,color='#dceaff',bold=false,max=width,size=font) {
    c.font=`${bold?'600 ':''}${size}px Arial`;c.fillStyle=color;
    let t=String(value);while(t && c.measureText(t).width>max)t=t.slice(0,-1);
    if(t!==String(value))t=t.slice(0,-1)+'…';c.fillText(t,x,y);
  }
  function box(x,y,w,h,title) {
    c.fillStyle='#0a1a2aed';c.fillRect(x,y,w,h);c.strokeStyle='#294b65';c.lineWidth=u;c.strokeRect(x,y,w,h);
    text(title,x+pad,y+line,'#65e4ff',true,w-pad*2);
  }
  const key=[['#ff6577','Tracked: not visible / unknown'],['#52f0b0','Tracking now, visible'],['#59aaff','Scheduled for later'],['#ffad5b','Previously tracked'],['#91a4b8','Not scheduled']];
  function legend(x,y,w) {
    box(x,y,w,line*6.7,'SATELLITE STATUS');
    key.forEach(([color,label],i)=>{const yy=y+line*(2+i*.9);c.fillStyle=color;c.beginPath();c.arc(x+pad,yy-font*.3,3.8*u,0,Math.PI*2);c.fill();text(label,x+pad+13*u,yy,'#c7d9e9',false,w-pad*2-13*u);});
  }
  function antennaValue(a) {
    const value=a.antenna??a.antenna_id??a.field_3;
    const match=String(value??'').match(/\d+/);
    return match?Number(match[0]):Infinity;
  }
  const active=(schedule.assignments||[]).filter(a=>assignmentActive(a,expected)).sort((a,b)=>{
    const av=antennaValue(a),bv=antennaValue(b);
    if(av!==bv)return av<bv?-1:1;
    return String(a.satellite_id).localeCompare(String(b.satellite_id),undefined,{numeric:true}) || a.startMs-b.startMs;
  });
  if(hasRight) {
    const x=sideX+pad,w=sideW-pad*2,bottom=height-footH-pad;let y=pad;
    box(x,y,w,line*2.7,'MISSION TRACKING');
    text(`${active.length} active contacts · 3° mask`,x+pad,y+line*2,'#acc4db',false,w-pad*2);y+=line*2.7+pad;
    if(sidebar.coverage) {
      const locs=coverageLocations(),shown=locs.slice(0,4);
      const h=line*(1.7+shown.length*.9+(locs.length>shown.length ? 0.8 : 0));
      box(x,y,w,h,'TRACKED LOCATION COVERAGE');
      shown.forEach((p,i)=>{
        const ids=[...new Set(active.map(a=>String(a.satellite_id)))];
        const views=ids.map(id=>orbitById.get(id)?.location_visibility?.[p.id]);
        const count=views.filter(v=>v?.visible===true).length,unknown=views.filter(v=>!v).length;
        text(`${p.name}  ${count}${unknown?' + ?':''} tracked`,x+pad,y+line*(2+i*.9),count>=3?'#52f0b0':count===2?'#ffe279':'#ffad5b',false,w-pad*2);
      });
      if(locs.length>shown.length)text(`+${locs.length-shown.length} locations`,x+pad,y+h-line*.3,'#8fa9be',false,w-pad*2);
      y+=h+pad;
    }
    if(sidebar.assignments) {
      const h=Math.max(line*2,bottom-y);
      box(x,y,w,h,'ACTIVE CONTACTS / ANTENNAS');
      const count=Math.max(1,active.length),rowH=(h-line*1.5)/count;
      const size=Math.min(font,Math.max(7*u,rowH*.23));
      active.forEach((a,i)=>{
        const id=String(a.satellite_id),r=orbitById.get(id),meta=metadataFor(id),yy=y+line*1.8+i*rowH;
        const antenna=a.antenna??a.antenna_id??a.field_3??'?';
        const duration=Math.max(0,(a.endMs-a.startMs)/1000),remain=Math.max(0,(a.endMs-expected)/1000);
        text(`MEO ${meta.meosar_id||'?'} · ${meta.band||'?'} band · ANT ${antenna}`,x+pad,yy,r?satelliteColor(r):'#ff6577',true,w-pad*2,size);
        text(`NORAD ${id} · ${fmtDuration(duration)} duration`,x+pad,yy+size*1.35,'#b6ccdf',false,w-pad*2,size);
        text(`${fmtTime(a.startMs).replace(' UTC','')} → ${fmtTime(a.endMs).replace(' UTC','')} · ${fmtDuration(remain)} left`,x+pad,yy+size*2.7,'#8fa9be',false,w-pad*2,size);
        const fraction=Math.max(0,Math.min(1,(expected-a.startMs)/Math.max(1,a.endMs-a.startMs)));
        c.fillStyle='#243e54';c.fillRect(x+pad,yy+size*3.1,w-pad*2,2*u);c.fillStyle='#52f0b0';c.fillRect(x+pad,yy+size*3.1,(w-pad*2)*fraction,2*u);
      });
      if(!active.length)text('No active contacts',x+pad,y+line*2,'#8fa9be',false,w-pad*2);
      y+=h+pad;
    }
  }
  // Mission context and key share the protected left margin in every export.
  if(hasInfo) {
  box(pad,pad,keyWidth,infoHeight,compactInfo?'MISSION SUMMARY':'MISSION INFORMATION');
  let infoY=pad+line*1.8;
  for(const row of infoRows) {
    text(row.label,pad*2,infoY,'#82a6c2',true,keyWidth-2*pad,infoFont*.74);
    infoY+=infoFont*.95;
    for(const value of row.lines) {
      text(value,pad*2,infoY,'#e0edf8',false,keyWidth-2*pad,infoFont);infoY+=infoFont*1.22;
    }
    infoY+=infoFont*.55;
  }
  }
  if(hasKey)legend(pad,pad+(hasInfo?infoHeight+pad:0),keyWidth);
  // Single mission timeline: no per-satellite rows.
  if(dashboard) {
    const first=sidebar.first??schedule.startMs,last=sidebar.last??schedule.endMs;
    const span=Math.max(1,last-first),fraction=Math.max(0,Math.min(1,(expected-first)/span));
    const y=height-footH;
    c.fillStyle='#081625f5';c.fillRect(0,y,width,footH);
    const mutual=new Set(orbitResults.filter(r=>r.visibility?.visible===true && r.location_visibility?.mission?.visible===true).map(r=>String(r.satellite_id??r.norad_id))).size;
    text(`${fmtDate(expected)}  ${fmtTime(expected)}`,pad,y+line,'#edf7ff',true,width*.46);
    text(`${Number(sidebar.speed||1).toFixed(2)}× · ${mutual} mutually visible`,width*.53,y+line,'#65e4ff',true,width*.45);
    const x=pad,w=width-pad*2,barY=y+line*1.65;
    c.fillStyle='#263f56';c.fillRect(x,barY,w,4*u);c.fillStyle='#47dff4';c.fillRect(x,barY,w*fraction,4*u);
    c.fillStyle='#f0fbff';c.beginPath();c.arc(x+w*fraction,barY+2*u,5*u,0,Math.PI*2);c.fill();
    text(`${fmtDate(first)} ${fmtTime(first)}`,pad,height-8*u,'#91abc3',false,width*.48,font*.85);
    const endText=`${fmtDate(last)} ${fmtTime(last)}`;c.font=`${font*.85}px Arial`;
    text(endText,width-pad-c.measureText(endText).width,height-8*u,'#91abc3',false,width*.48,font*.85);
  }
  // Globe-only intentionally has no added key, timeline or timestamp overlay.
  return {png:image.toDataURL('image/png').split(',')[1],time:expected,width,height,smartMargins:plan};
}

function finishVideoExport() {
  if(!videoExportSnapshot) return;
  ({playing,simTimeMs,globeYaw,globePitch,globeZoom,showCoverage,showGroundTracks,showOrbitPaths}=videoExportSnapshot);
  videoFixedLayout=null;
  videoExportSnapshot=null;document.body.style.pointerEvents='';lastFrame=0;
  if(videoDialogPlaying!==null) playing=false;
  if(videoDialogResumePending) resumeVideoDialog();
  updateClock();refreshDashboard();requestOrbitUpdate(true);
}

