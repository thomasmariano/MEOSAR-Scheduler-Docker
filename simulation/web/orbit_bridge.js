function setOrbitData(results) {
  orbitResults = Array.isArray(results) ? results : [];
  orbitById = new Map();

  for (const r of orbitResults) {
    orbitById.set(
      String(r.satellite_id ?? r.norad_id ?? ""),
      r
    );
  }

  const frameTime = orbitResults.find(r => r.simulation_time_utc)?.simulation_time_utc;
  dataTimeMs = frameTime && Number.isFinite(Date.parse(frameTime)) ? Date.parse(frameTime) : null;
  if (orbitResults.some(r => !r.error && Array.isArray(r.ecef_km))) {
    setStatus("SGP4 POSITIONS AVAILABLE", "good");
    $("globeBadge").textContent = "UTC · ALTITUDE COMPRESSED";
  } else setStatus(orbitResults.length ? "NO PLOTTABLE POSITIONS" : "WAITING FOR ORBIT DATA");


  updateIssueHistory();
  updateExtraWidgets();
  refreshDashboard();
}

function setOrbitError(message) {
  const msg = String(message || "Unknown orbit engine error");
  if (msg !== lastOrbitError) {
    lastOrbitError = msg;
    addDiagnostic("Orbit update failed",msg,"error");
  }
  setStatus("ORBIT UPDATE ERROR","bad");
}
function setStation(data) {
  if (activeNavigationId !== null) cancelCoverageNavigation('Ground station changed; run the search again.');
  station = data || null;
  refreshDashboard();
}

function setLandingSite(data) {
  if (activeNavigationId !== null) cancelCoverageNavigation('Mission site changed; run the search again.');
  landingSite = data || null;
  refreshDashboard();
}
function requestOrbitUpdate(force=false) {
  if (typeof window.qtBridgeRequestOrbitUpdate === "function") window.qtBridgeRequestOrbitUpdate();
  // Python polls the simulation clock. This function is intentionally harmless
  // when no custom Qt bridge is installed.
}

