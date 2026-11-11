let earthSurfaceCacheKey = null;
let globeDrawQueued = false;
function queueGlobeDraw() {
  if (globeDrawQueued) return;
  globeDrawQueued = true;
  requestAnimationFrame(() => { globeDrawQueued = false; drawGlobe(); });
}

function drawTexturedEarth(cx, cy, R) {
    // Limit rendering resolution to keep mouse rotation responsive.
    const size = Math.max(
        globeDragging ? 220 : 300,
        Math.min(globeDragging ? 340 : 850, Math.ceil(2 * R))
    );

    if (
        earthRenderCanvas.width !== size ||
        earthRenderCanvas.height !== size
    ) {
        earthRenderCanvas.width = size;
        earthRenderCanvas.height = size;
    }



    const radius = size / 2;
    const cosYaw = Math.cos(globeYaw);
    const sinYaw = Math.sin(globeYaw);
    const cosPitch = Math.cos(globePitch);
    const sinPitch = Math.sin(globePitch);
    

    // Surface counts use all active assignments, irrespective of display switches.
    // A layer switch masks painting only; it does not change physical counts.
    const coverageSatellites = [];
    const earthRadiusKm = 6378.137;
    const eccentricitySquared = (1/298.257223563)*(2-1/298.257223563);
    const minimumElevationSineSquared = Math.sin(3*Math.PI/180)**2;
    if (showCoverage) {
      for (const r of orbitResults) {
        if (r.error || !Array.isArray(r.ecef_km) || r.ecef_km.length < 3 || !r.ecef_km.every(Number.isFinite)) continue;
        const active = trackingState(satelliteId(r), dataTimeMs ?? simTimeMs).active;
        const paint = layerVisible(r, "coverage") && (!activeCoverageOnly || active);
        if (!active && !paint) continue;
        coverageSatellites.push({xyz:r.ecef_km, active, paint});
      }
    }


    const surfaceKey = JSON.stringify([size, globeYaw, globePitch,
      earthTextureWidth, earthTextureHeight, coverageSatellites]);
    if (surfaceKey !== earthSurfaceCacheKey) {
    const output = earthRenderCtx.createImageData(size, size);
    const pixels = output.data;
    for (let py = 0; py < size; py++) {
        const screenY = (radius - py - 0.5) / radius;

        for (let px = 0; px < size; px++) {
            const screenZ = (px + 0.5 - radius) / radius;
            const distanceSquared =
                screenY * screenY + screenZ * screenZ;

            if (distanceSquared > 1) {
                continue;
            }

            // Recover the visible hemisphere's depth.
            const depth = Math.sqrt(1 - distanceSquared);

            // Invert the globe's pitch rotation.
            const x1 = depth * cosPitch - screenY * sinPitch;
            const vy = depth * sinPitch + screenY * cosPitch;

            // Invert its yaw rotation.
            const vx = x1 * cosYaw + screenZ * sinYaw;
            const vz = -x1 * sinYaw + screenZ * cosYaw;

            const latitude = Math.asin(
                Math.max(-1, Math.min(1, vy))
            );

            const longitude = Math.atan2(vz, vx);

            const textureWidth = earthTextureWidth || 1;
            const textureHeight = earthTextureHeight || 1;
            let tx = Math.floor(((longitude/(2*Math.PI))+0.5)*textureWidth);
            tx = ((tx % textureWidth)+textureWidth)%textureWidth;
            const ty = Math.max(0,Math.min(textureHeight-1,Math.floor((0.5-latitude/Math.PI)*textureHeight)));
            const sourceIndex = (ty*textureWidth+tx)*4;

            const targetIndex = (py * size + px) * 4;

            // Soft directional lighting for a spherical appearance.
            const light = Math.max(
                0.30,
                Math.min(
                    1.0,
                    0.52 +
                    0.48 * (
                        0.65 * depth +
                        0.45 * screenY +
                        0.30 * screenZ
                    )
                )
            );


            let red = (earthTexturePixels ? earthTexturePixels[sourceIndex] : 15)*light;
            let green = (earthTexturePixels ? earthTexturePixels[sourceIndex+1] : 52)*light;
            let blue = (earthTexturePixels ? earthTexturePixels[sourceIndex+2] : 80)*light;

            // The visible surface direction maps to geodetic latitude/longitude.
            // WGS84 observer coordinates + local up match OrbitEngine at sea level.
            let trackedCount = 0, painted = false;
            if (coverageSatellites.length) {
              const n = earthRadiusKm/Math.sqrt(1-eccentricitySquared*vy*vy);
              const gx=n*vx, gy=n*vz, gz=n*(1-eccentricitySquared)*vy;
              for (const satellite of coverageSatellites) {
                const dx=satellite.xyz[0]-gx, dy=satellite.xyz[1]-gy, dz=satellite.xyz[2]-gz;
                const up=dx*vx+dy*vz+dz*vy;
                if (up < 0 || up*up < (dx*dx+dy*dy+dz*dz)*minimumElevationSineSquared) continue;
                if (satellite.active) trackedCount++;
                if (satellite.paint) painted=true;
              }
            }
            if (painted) {
              const color = trackedCount >= 3 ? [82,240,176] : trackedCount === 2 ? [255,209,102] : trackedCount === 1 ? [255,155,69] : [85,153,255];
              const alpha = trackedCount > 0 ? 0.32 : 0.10;
              red=red*(1-alpha)+color[0]*alpha;
              green=green*(1-alpha)+color[1]*alpha;
              blue=blue*(1-alpha)+color[2]*alpha;
            }

            pixels[targetIndex] = red;
            pixels[targetIndex + 1] = green;
            pixels[targetIndex + 2] = blue;
            pixels[targetIndex + 3] = 255;

        }
    }

    earthRenderCtx.putImageData(output, 0, 0);
    earthSurfaceCacheKey = surfaceKey;
    }

    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.clip();

    ctx.drawImage(
        earthRenderCanvas,
        cx - R,
        cy - R,
        R * 2,
        R * 2
    );

    ctx.restore();
}

function drawGlobe() {
  if (!canvas) {
    canvas = $("globeCanvas");
    if (!canvas) return;
    ctx = canvas.getContext("2d");
  }

  const rect = canvas.getBoundingClientRect();
  if (rect.width < 5 || rect.height < 5) return;

  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(rect.width * dpr);
  const h = Math.round(rect.height * dpr);

  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const W = rect.width;
  const H = rect.height;

  ctx.clearRect(0, 0, W, H);

  // Space background.
  const background = ctx.createRadialGradient(
    W * 0.48, H * 0.45, 5,
    W * 0.48, H * 0.45, Math.max(W, H)
  );

  background.addColorStop(0, "#101f35");
  background.addColorStop(1, "#03060c");

  ctx.fillStyle = background;
  ctx.fillRect(0, 0, W, H);

  // Background stars.
  for (let i = 0; i < 180; i++) {
    const x = ((i * 137.508 + 29) % 997) / 997 * W;
    const y = ((i * 71.31 + 17) % 991) / 991 * H;
    const radius = i % 9 === 0 ? 1.25 : 0.65;

    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(190,220,255,${0.12 + (i % 5) * 0.1})`;
    ctx.fill();
  }

  const cx = W * 0.5;
  const cy = H * 0.51;
  const R = Math.min(H * 0.40, W * 0.34, 250) * globeZoom;

  if (R < 10) return;

  const cosYaw = Math.cos(globeYaw);
  const sinYaw = Math.sin(globeYaw);
  const cosPitch = Math.cos(globePitch);
  const sinPitch = Math.sin(globePitch);

  // Rotate a 3D Earth-centered vector into the camera view.
  // x is camera depth, y is north, and z is screen horizontal.
  function projectVector(vx, vy, vz, radius = R) {
    const x1 = vx * cosYaw - vz * sinYaw;
    const z1 = vx * sinYaw + vz * cosYaw;

    const depth = x1 * cosPitch + vy * sinPitch;
    const y2 = vy * cosPitch - x1 * sinPitch;

    return {
      x: cx + radius * z1,
      y: cy - radius * y2,
      depth
    };
  }

  function projectLatLon(lat, lon, radius = R) {
    const latR = lat * Math.PI / 180;
    const lonR = lon * Math.PI / 180;

    return projectVector(
      Math.cos(latR) * Math.cos(lonR),
      Math.sin(latR),
      Math.cos(latR) * Math.sin(lonR),
      radius
    );
  }

  // Atmospheric halo.
  const atmosphere = ctx.createRadialGradient(
    cx, cy, R * 0.83,
    cx, cy, R * 1.14
  );

  atmosphere.addColorStop(0, "#238bd022");
  atmosphere.addColorStop(0.65, "#239fff18");
  atmosphere.addColorStop(1, "#239fff00");

  ctx.beginPath();
  ctx.arc(cx, cy, R * 1.14, 0, Math.PI * 2);
  ctx.fillStyle = atmosphere;
  ctx.fill();


  function projectSatellite(ecef) {
    const vector = satelliteDisplayVector(ecef);
    return vector ? projectVector(...vector) : null;
  }

  const trackLabelPositions = [];
  function faintTrackLabel(point, id, kind, selected) {
    if (!point || point.depth <= 0 || point.x < 12 || point.y < 18 || point.x > W-120 || point.y > H-22) return;
    if (trackLabelPositions.some(p => Math.hypot(p.x-point.x,p.y-point.y)<85)) return;
    trackLabelPositions.push(point);
    ctx.save(); ctx.globalAlpha=selected ? 0.85 : 0.38;
    ctx.font="10px Arial"; ctx.lineWidth=3;
    const label=`${satelliteLabel(id)} · ${kind}`;
    ctx.strokeStyle="#030911"; ctx.strokeText(label,point.x+5,point.y-5);
    ctx.fillStyle="#d9eaff"; ctx.fillText(label,point.x+5,point.y-5);
    ctx.restore();
  }
  function drawOrbitPass(front) {
    if (!showOrbitPaths) return;
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const orbit of orbitPaths) {
      const satellite = orbitById.get(String(orbit.satellite_id));
      if (!layerVisible(satellite, "orbit")) continue;
      const points = orbit.orbit_points;
      if (!Array.isArray(points) || points.length < 2) continue;
      const selected = String(orbit.satellite_id) === String(selectedId);
      ctx.strokeStyle = satelliteColor(satellite);
      ctx.globalAlpha = selected ? 0.95 : front ? 0.48 : 0.22;
      ctx.lineWidth = selected ? 2 : 1.1;
      ctx.setLineDash(front ? [] : [4, 5]);
      ctx.beginPath();
      let previous = null;
      for (const point of points) {
        const current = projectSatellite(point);
        const segment = hemisphereSegment(previous, current, front);
        if (segment) {
          ctx.moveTo(segment[0].x, segment[0].y);
          ctx.lineTo(segment[1].x, segment[1].y);
        }
        previous = current;
      }
      ctx.stroke();
      if (front) {
        const anchor = points.map(projectSatellite).find(p => p && p.depth>0.25);
        faintTrackLabel(anchor, orbit.satellite_id, "orbit", selected);
      }
    }
    ctx.restore();
  }

  // Back portions are occluded by Earth; front portions are drawn afterward.
  drawOrbitPass(false);
  drawTexturedEarth(cx, cy, R);

  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.clip();

  if (showGroundTracks) {
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const orbit of orbitPaths) {
      const satellite = orbitById.get(String(orbit.satellite_id));
      if (!layerVisible(satellite, "ground")) continue;
      const track = orbit.ground_track;
      if (!Array.isArray(track) || track.length < 2) continue;
      const selected = String(orbit.satellite_id) === String(selectedId);
      const times = orbit.sample_times_ms || [];
      // Use the position timestamp so styles match the last propagated frame.
      const currentTime = Date.parse(satellite?.simulation_time_utc) || simTimeMs;
      for (const future of [false, true]) {
        ctx.beginPath();
        for (let i = 1; i < track.length; i++) {
          const a = track[i-1], b = track[i];
          if (!Array.isArray(a) || !Array.isArray(b) ||
              !a.slice(0, 2).every(Number.isFinite) ||
              !b.slice(0, 2).every(Number.isFinite)) continue;
          // Subdivide on the sphere. Longitude wrapping needs no special break.
          const toVector = point => {
            const lat = point[0]*Math.PI/180, lon = point[1]*Math.PI/180;
            return [Math.cos(lat)*Math.cos(lon), Math.sin(lat),
                    Math.cos(lat)*Math.sin(lon)];
          };
          const va = toVector(a), vb = toVector(b);
          let previous = null;
          for (let j = 0; j <= 4; j++) {
            const f = j/4;
            const vector = va.map((value, k) => value*(1-f)+vb[k]*f);
            const norm = Math.hypot(...vector);
            if (norm < 1e-8) { previous = null; continue; }
            const current = projectVector(...vector.map(value => value/norm));
            const sampleTime = Number.isFinite(times[i-1]) && Number.isFinite(times[i])
              ? times[i-1] + (times[i]-times[i-1])*Math.max(0, (j-0.5)/4)
              : currentTime;
            if ((sampleTime > currentTime) === future) {
              const segment = hemisphereSegment(previous, current, true);
              if (segment) {
                ctx.moveTo(segment[0].x, segment[0].y);
                ctx.lineTo(segment[1].x, segment[1].y);
              }
            }
            previous = current;
          }
        }
        ctx.strokeStyle = satelliteColor(satellite);
        ctx.globalAlpha = selected ? (future ? 0.8 : 1) : (future ? 0.35 : 0.65);
        ctx.lineWidth = selected ? 2.2 : 1.2;
        ctx.setLineDash(future ? [4, 5] : []);
        ctx.stroke();
      }
      const trackAnchor = track.map(p => projectLatLon(p[0],p[1])).find(p => p && p.depth>0.35);
      faintTrackLabel(trackAnchor, orbit.satellite_id, "ground", selected);
      // Mark the current subpoint on the surface.
      const subpoint = satellite?.subpoint;
      if (Number.isFinite(subpoint?.latitude) && Number.isFinite(subpoint?.longitude)) {
        const p = projectLatLon(subpoint.latitude, subpoint.longitude);
        if (p.depth > 0) {
          ctx.globalAlpha = 0.9;
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.arc(p.x, p.y, selected ? 3.5 : 2, 0, Math.PI*2);
          ctx.fillStyle = satelliteColor(satellite);
          ctx.fill();
        }
      }
    }
  }
  ctx.restore();

ctx.save();
ctx.beginPath();
ctx.arc(cx, cy, R, 0, Math.PI * 2);
ctx.clip();

  // Latitude and longitude graticule.
  ctx.strokeStyle = "#83dcff32";
  ctx.lineWidth = 0.7;

  for (let lat = -75; lat <= 75; lat += 15) {
    ctx.beginPath();
    let drawing = false;

    for (let lon = -180; lon <= 180; lon += 2) {
      const p = projectLatLon(lat, lon);

      if (p.depth <= 0) {
        drawing = false;
        continue;
      }

      if (!drawing) {
        ctx.moveTo(p.x, p.y);
        drawing = true;
      } else {
        ctx.lineTo(p.x, p.y);
      }
    }

    ctx.stroke();
  }

  for (let lon = -180; lon < 180; lon += 15) {
    ctx.beginPath();
    let drawing = false;

    for (let lat = -90; lat <= 90; lat += 2) {
      const p = projectLatLon(lat, lon);

      if (p.depth <= 0) {
        drawing = false;
        continue;
      }

      if (!drawing) {
        ctx.moveTo(p.x, p.y);
        drawing = true;
      } else {
        ctx.lineTo(p.x, p.y);
      }
    }

    ctx.stroke();
  }

  ctx.restore();

  // Crisp Earth outline.
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.strokeStyle = "#65caff";
  ctx.lineWidth = 1.4;
  ctx.stroke();

  // Ground station marker.
  if (
    station &&
    Number.isFinite(Number(station.latitude)) &&
    Number.isFinite(Number(station.longitude))
  ) {
    const p = projectLatLon(
      Number(station.latitude),
      Number(station.longitude),
      R * 1.002
    );

    if (p.depth > 0) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = "#ffbd69";
      ctx.fill();

      ctx.beginPath();
      ctx.arc(p.x, p.y, 9, 0, Math.PI * 2);
      ctx.strokeStyle = "#ffbd6980";
      ctx.stroke();

    }
  }


  // Landing-site marker.
  if (
    landingSite &&
    Number.isFinite(Number(landingSite.latitude)) &&
    Number.isFinite(Number(landingSite.longitude))
  ) {
    const p = projectLatLon(
      Number(landingSite.latitude),
      Number(landingSite.longitude),
      R * 1.003
    );

    if (p.depth > 0) {
      // Diamond marker to distinguish the landing site from the station.
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(Math.PI / 4);

      ctx.fillStyle = "#ff647c";
      ctx.fillRect(-4.5, -4.5, 9, 9);

      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1;
      ctx.strokeRect(-4.5, -4.5, 9, 9);

      ctx.restore();

      ctx.beginPath();
      ctx.arc(p.x, p.y, 10, 0, Math.PI * 2);
      ctx.strokeStyle = "#ff647c99";
      ctx.lineWidth = 1.3;
      ctx.stroke();

    }
  }


  for (const location of coverageLocations()) {
    const p = projectLatLon(Number(location.latitude), Number(location.longitude), R*1.004);
    if (p.depth <= 0) continue;
    const summary = coverageSummary(location);
    ctx.save();
    ctx.strokeStyle = summary.color;
    ctx.fillStyle = summary.color;
    ctx.lineWidth = 2.5;
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.arc(p.x,p.y,9,0,Math.PI*2); ctx.stroke();
    const text=`${location.name}: ${summary.ready ? summary.count : '…'} tracked`;
    ctx.font="600 11px Arial";
    const textWidth=Math.min(W-28, (ctx.measureText(text)?.width || text.length*6.5));
    const labelX=Math.max(8,Math.min(p.x+13,W-textWidth-14));
    const labelY=Math.max(22,Math.min(p.y-10,H-22));
    ctx.fillStyle="rgba(3, 8, 16, 0.90)";
    ctx.fillRect(labelX-5,labelY-13,textWidth+10,19);
    ctx.fillStyle="#ffffff";
    ctx.fillText(text,labelX,labelY,textWidth);
    ctx.restore();
  }

  drawOrbitPass(true);

  // Plot Earth-fixed satellite positions.
  satelliteHits = [];

  const usable = orbitResults.filter(r =>
    !r.error &&
    Array.isArray(r.ecef_km) &&
    r.ecef_km.length >= 3 &&
    r.ecef_km.every(Number.isFinite) &&
    layerVisible(r, "marker")
  );


  for (const r of usable) {
    const [x, y, z] = r.ecef_km;
    const norm = Math.hypot(x, y, z);

    if (!norm) continue;

    // Use exactly the same coordinate mapping and scale as orbital paths.
    const p = projectSatellite(r.ecef_km);
    if (!p) continue;
    // A far-side satellite remains visible if it projects outside Earth's disk.
    if (p.depth < 0 && Math.hypot(p.x-cx, p.y-cy) < R) continue;

const isVisible = !!r.visibility?.visible;
const isSelected = String(r.satellite_id) === String(selectedId);
const isScheduled = !!r.scheduled;

const color = satelliteColor(r);
    const dotRadius = isSelected ? 5.5 : 3.5;
    satelliteHits.push({id:satelliteId(r), x:p.x, y:p.y, labelWidth:satelliteLabel(satelliteId(r)).length*7});

    ctx.beginPath();
    ctx.arc(p.x, p.y, dotRadius, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = isSelected ? 18 : 10;
    ctx.fill();
    ctx.shadowBlur = 0;

    if (isSelected) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 10, 0, Math.PI * 2);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1.3;
      ctx.stroke();
    }

    ctx.font = "10px monospace";
    ctx.fillStyle = color;
    ctx.fillText(satelliteLabel(satelliteId(r)), p.x + 7, p.y - 7);
  }

  if (!usable.length) {
    ctx.textAlign = "center";
    ctx.fillStyle = "#d6e8ff";
    ctx.font = "600 12px Arial";
    ctx.fillText(
      "EARTH RENDERED · WAITING FOR ORBIT POSITIONS",
      cx,
      cy + R + 23
    );
    ctx.textAlign = "start";
  }

  // Camera hint.
  ctx.fillStyle = "#c6ddf899";
  ctx.font = "10px Arial";
  ctx.fillText(
    `ZOOM ${Math.round(globeZoom * 100)}%  ·  DRAG TO ROTATE`,
    13,
    H - 13
  );
}

let lastTimelineRefresh = 0;
function frame(t) {
  if (playing && schedule) {
    if (!lastFrame) lastFrame=t;
    const dt=Math.min(250,t-lastFrame);
    simTimeMs += dt*speed;
    if (simTimeMs>=schedule.endMs) {
      simTimeMs=schedule.endMs;playing=false;$("playButton").textContent="▶ PLAY";
    }
    lastFrame=t;
    updateClock();
    if (!playing || t-lastTimelineRefresh > 150) {
      updateExtraWidgets();
      renderSchedule(); lastTimelineRefresh = t;
    }
    if (t-lastDynamicRefresh>150) {
      lastDynamicRefresh=t;
      const signature = JSON.stringify((schedule.satellite_ids || []).map(id => trackingState(id)));
      if (signature !== lastTrackingSignature) {
        lastTrackingSignature=signature;
        refreshDashboard();
      }
    }
    if (t-lastOrbitUpdate>850) {
      lastOrbitUpdate=t;
      requestOrbitUpdate();
    }
  } else {
    lastFrame=t;
  }
  requestAnimationFrame(frame);
}

canvas = $("globeCanvas");
ctx = canvas.getContext("2d");

canvas.style.cursor = "grab";
canvas.style.touchAction = "none";

// Click and drag to rotate the globe.
canvas.addEventListener("pointerdown", event => {
  if (event.button !== 0) return;
  globeDragging = true;
  globeMoved = false;
  pointerDownX = event.clientX;
  pointerDownY = event.clientY;
  const rect = canvas.getBoundingClientRect();
  pointerSatelliteId = findSatelliteHit(event.clientX-rect.left,event.clientY-rect.top)?.id || null;
  globeLastX = event.clientX;
  globeLastY = event.clientY;

  canvas.style.cursor = "grabbing";
  canvas.setPointerCapture(event.pointerId);
});

canvas.addEventListener("pointermove", event => {
  if (!globeDragging) {
    const rect = canvas.getBoundingClientRect();
    const hit = findSatelliteHit(event.clientX-rect.left,event.clientY-rect.top);
    canvas.style.cursor = hit ? "pointer" : "grab";
    canvas.title = hit ? labelDescription(hit.id) : "Drag to rotate; click a satellite or its label to inspect";
    return;
  }
  if (!globeMoved && Math.hypot(event.clientX-pointerDownX,event.clientY-pointerDownY) < 5) return;

  const dx = event.clientX - globeLastX;
  const dy = event.clientY - globeLastY;

  if (Math.abs(dx) + Math.abs(dy) > 0.5) {
    globeMoved = true;
  }

  globeYaw += dx * 0.008;
  globePitch += dy * 0.008;

  // Avoid flipping the globe upside down.
  globePitch = Math.max(
    -Math.PI / 2 + 0.05,
    Math.min(Math.PI / 2 - 0.05, globePitch)
  );

  globeLastX = event.clientX;
  globeLastY = event.clientY;

  queueGlobeDraw();
});

function stopGlobeDrag(event) {
  if (globeDragging && !globeMoved && event?.type === "pointerup") {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX-rect.left, y = event.clientY-rect.top;
    const hit = findSatelliteHit(x,y);
    const id = pointerSatelliteId || hit?.id;
    if (id) selectSatellite(id);
  }
  pointerSatelliteId = null;
  globeDragging = false;
  queueGlobeDraw();
  canvas.style.cursor = "grab";
}

canvas.addEventListener("pointerup", stopGlobeDrag);
canvas.addEventListener("pointercancel", stopGlobeDrag);

// Scroll up to zoom in; scroll down to zoom out.
canvas.addEventListener("wheel", event => {
  event.preventDefault();

  const zoomFactor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
  globeZoom = Math.max(0.50, Math.min(2.6, globeZoom * zoomFactor));

  queueGlobeDraw();
}, { passive: false });


window.addEventListener("resize", drawGlobe);
document.querySelector('aside.right').addEventListener('click',event=>{
  const select=event.target.closest('[data-contact-select]');if(select)selectSatellite(select.dataset.contactSelect);
  const jump=event.target.closest('[data-contact-time]');if(jump)jumpToSimulationTime(Number(jump.dataset.contactTime));
});

window.addEventListener("error", e => {
  addDiagnostic(
    "Dashboard JavaScript error",
    e.message || "Unknown JavaScript error",
    "error"
  );
});

$("comparisonRows").addEventListener("click", event => {
  const button=event.target.closest("[data-comparison]");
  if(button) selectSatellite(button.dataset.comparison);
});
$("satelliteLayers").addEventListener("change", event => {
  const target = event.target;
  if (target.dataset.satellite && target.dataset.layer) setSatelliteOption(target.dataset.satellite, target.dataset.layer, target.checked);
});
$("satelliteLayers").addEventListener("click", event => {
  const button = event.target.closest("[data-select]");
  if (button) selectSatellite(button.dataset.select);
});

// Draw immediately; do not wait for the texture or orbit data.
drawGlobe();

renderDiagnostics();
requestAnimationFrame(frame);

