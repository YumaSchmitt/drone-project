/* ===================================================================
   Drone Farmland Cutter — frontend JS
   =================================================================== */

// ------------------------------------------------------------------ //
// Map setup                                                           //
// ------------------------------------------------------------------ //
const map = L.map("map", { zoomControl: true }).setView([36.500581661518986, 140.33317567868494], 14);

L.tileLayer("https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", {
  attribution: 'Imagery &copy; Google',
  maxZoom: 21,
  maxNativeZoom: 21,
}).addTo(map);

// Drawing state
let drawingMode = false;
let drawnPoints  = [];       // [{lat, lng}]
let drawnMarkers = [];
let drawnPolyline = null;
let drawnPolygon  = null;
let importedPolygons = [];   // from KML
let selectedPolyIndex = -1;

// ------------------------------------------------------------------ //
// Card collapse toggle                                                //
// ------------------------------------------------------------------ //
document.querySelectorAll(".card-header").forEach(hdr => {
  hdr.addEventListener("click", () => {
    hdr.closest(".card").classList.toggle("collapsed");
  });
});

// ------------------------------------------------------------------ //
// Tab switching                                                       //
// ------------------------------------------------------------------ //
document.querySelectorAll(".tabs").forEach(tabGroup => {
  tabGroup.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      const container = tab.closest(".card-body") || tab.closest(".tab-section");
      container.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
      container.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      container.querySelector(`.tab-panel[data-panel="${target}"]`).classList.add("active");
    });
  });
});

// ------------------------------------------------------------------ //
// GPS Bounds                                                          //
// ------------------------------------------------------------------ //
function setBounds(latMin, latMax, lonMin, lonMax) {
  document.getElementById("lat_min").value = latMin;
  document.getElementById("lat_max").value = latMax;
  document.getElementById("lon_min").value = lonMin;
  document.getElementById("lon_max").value = lonMax;
  fitMapToBounds(latMin, latMax, lonMin, lonMax);
}

function fitMapToBounds(latMin, latMax, lonMin, lonMax) {
  try {
    map.fitBounds([[latMin, lonMin], [latMax, lonMax]]);
  } catch (e) {}
}

// "Use demo values" button
document.getElementById("btn-demo-bounds").addEventListener("click", async () => {
  const res = await fetch("/api/demo-bounds");
  const d = await res.json();
  setBounds(d.lat_min, d.lat_max, d.lon_min, d.lon_max);
});

// Fit map when bounds change
["lat_min","lat_max","lon_min","lon_max"].forEach(id => {
  document.getElementById(id).addEventListener("change", () => {
    const lmin = parseFloat(document.getElementById("lat_min").value);
    const lmax = parseFloat(document.getElementById("lat_max").value);
    const nmin = parseFloat(document.getElementById("lon_min").value);
    const nmax = parseFloat(document.getElementById("lon_max").value);
    if ([lmin,lmax,nmin,nmax].every(v => !isNaN(v))) {
      fitMapToBounds(lmin, lmax, nmin, nmax);
    }
  });
});

// ------------------------------------------------------------------ //
// Drawing polygon on map                                              //
// ------------------------------------------------------------------ //
function startDrawing() {
  clearDrawnPolygon();
  drawingMode = true;
  map.getContainer().style.cursor = "crosshair";
  showHint("Click on the map to add boundary points. Double-click or click ✔ to finish.");
  showPtsBadge(0);
  document.getElementById("btn-start-draw").textContent = "✖ Cancel drawing";
  document.getElementById("btn-start-draw").onclick = cancelDrawing;
  document.getElementById("btn-finish-draw").style.display = "inline-flex";
}

function cancelDrawing() {
  drawingMode = false;
  clearDrawnPolygon();
  map.getContainer().style.cursor = "";
  hideHint();
  hidePtsBadge();
  document.getElementById("btn-start-draw").textContent = "✏️ Draw on map";
  document.getElementById("btn-start-draw").onclick = startDrawing;
  document.getElementById("btn-finish-draw").style.display = "none";
}

function finishDrawing() {
  if (drawnPoints.length < 3) {
    alert("Please add at least 3 points to define the farmland boundary.");
    return;
  }
  drawingMode = false;
  map.getContainer().style.cursor = "";
  hideHint();
  hidePtsBadge();
  // Draw filled polygon
  if (drawnPolyline) { map.removeLayer(drawnPolyline); drawnPolyline = null; }
  if (drawnPolygon)  { map.removeLayer(drawnPolygon);  drawnPolygon = null;  }
  drawnPolygon = L.polygon(drawnPoints.map(p => [p.lat, p.lng]), {
    color: "#2d6a4f", fillColor: "#52b788", fillOpacity: 0.25, weight: 2,
  }).addTo(map);
  document.getElementById("btn-start-draw").textContent = "✏️ Redraw";
  document.getElementById("btn-start-draw").onclick = startDrawing;
  document.getElementById("btn-finish-draw").style.display = "none";
  document.getElementById("draw-pts-count").textContent =
    `${drawnPoints.length} points defined`;
  selectedPolyIndex = -1; // drawn polygon takes priority
}

function clearDrawnPolygon() {
  drawnPoints = [];
  drawnMarkers.forEach(m => map.removeLayer(m));
  drawnMarkers = [];
  if (drawnPolyline) { map.removeLayer(drawnPolyline); drawnPolyline = null; }
  if (drawnPolygon)  { map.removeLayer(drawnPolygon);  drawnPolygon = null;  }
  document.getElementById("draw-pts-count").textContent = "";
}

map.on("click", e => {
  if (!drawingMode) return;
  drawnPoints.push(e.latlng);
  const marker = L.circleMarker(e.latlng, {
    radius: 5, color: "#2d6a4f", fillColor: "#52b788", fillOpacity: 1, weight: 2,
  }).addTo(map);
  drawnMarkers.push(marker);

  // Update preview polyline
  if (drawnPolyline) map.removeLayer(drawnPolyline);
  drawnPolyline = L.polyline(drawnPoints.map(p => [p.lat, p.lng]),
    { color: "#2d6a4f", weight: 2, dashArray: "5,4" }).addTo(map);

  showPtsBadge(drawnPoints.length);
});

map.on("dblclick", e => {
  if (!drawingMode) return;
  finishDrawing();
});

document.getElementById("btn-start-draw").addEventListener("click", startDrawing);
document.getElementById("btn-finish-draw").addEventListener("click", finishDrawing);
document.getElementById("btn-clear-draw").addEventListener("click", cancelDrawing);

// ------------------------------------------------------------------ //
// KML import                                                          //
// ------------------------------------------------------------------ //

function renderKmlPolygons(polygons) {
  importedPolygons = polygons;
  selectedPolyIndex = -1;

  const list = document.getElementById("kml-poly-list");
  list.innerHTML = "";
  document.getElementById("kml-poly-section").style.display = "block";

  polygons.forEach((poly, i) => {
    const item = document.createElement("div");
    item.className = "poly-item";
    item.innerHTML = `<span class="poly-name">${escHtml(poly.name)}</span>
      <span class="poly-pts">${poly.coordinates.length} pts</span>`;
    item.addEventListener("click", () => selectKmlPoly(i));
    list.appendChild(item);
  });

  // Auto-select if only one polygon
  if (polygons.length === 1) selectKmlPoly(0);
}

function selectKmlPoly(index) {
  selectedPolyIndex = index;
  document.querySelectorAll(".poly-item").forEach((el, i) => {
    el.classList.toggle("selected", i === index);
  });

  // Show polygon on map
  if (drawnPolygon) { map.removeLayer(drawnPolygon); drawnPolygon = null; }
  clearDrawnPolygon();

  const poly = importedPolygons[index];
  const latlngs = poly.coordinates.map(([lat, lon]) => [lat, lon]);
  drawnPolygon = L.polygon(latlngs, {
    color: "#40916c", fillColor: "#74c69d", fillOpacity: 0.3, weight: 2,
  }).addTo(map);
  map.fitBounds(drawnPolygon.getBounds().pad(0.3));
}

// KML file upload
document.getElementById("kml-file-input").addEventListener("change", async function() {
  const file = this.files[0];
  if (!file) return;
  setKmlStatus("Parsing KML …", "");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/parse-kml", { method: "POST", body: fd });
    const data = await res.json();
    if (data.error) { setKmlStatus(data.error, "error"); return; }
    setKmlStatus(`Found ${data.polygons.length} polygon(s)`, "ok");
    renderKmlPolygons(data.polygons);
  } catch (e) {
    setKmlStatus("Upload failed: " + e.message, "error");
  }
});

// Google My Maps URL fetch
document.getElementById("btn-fetch-kml").addEventListener("click", async () => {
  const url = document.getElementById("kml-url-input").value.trim();
  if (!url) return;
  setKmlStatus("Fetching …", "");
  try {
    const res = await fetch("/api/fetch-kml", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (data.error) { setKmlStatus(data.error, "error"); return; }
    setKmlStatus(`Found ${data.polygons.length} polygon(s)`, "ok");
    renderKmlPolygons(data.polygons);
  } catch (e) {
    setKmlStatus("Fetch failed: " + e.message, "error");
  }
});

function setKmlStatus(msg, type) {
  const el = document.getElementById("kml-status");
  el.textContent = msg;
  el.className = type === "error" ? "error-msg" : "hint";
}

// ------------------------------------------------------------------ //
// Process                                                             //
// ------------------------------------------------------------------ //
let pollTimer = null;

document.getElementById("btn-process").addEventListener("click", async () => {
  // Collect polygon
  let polygon;
  if (selectedPolyIndex >= 0 && importedPolygons.length > 0) {
    polygon = importedPolygons[selectedPolyIndex].coordinates; // [[lat,lon],...]
  } else if (drawnPoints.length >= 3 || drawnPolygon) {
    if (drawnPoints.length >= 3) {
      polygon = drawnPoints.map(p => [p.lat, p.lng]);
    } else {
      setProcessError("Please draw or import a farmland polygon first.");
      return;
    }
  } else {
    setProcessError("Please draw a polygon on the map or import a KML file.");
    return;
  }

  // Validate GPS bounds
  const latMin = parseFloat(document.getElementById("lat_min").value);
  const latMax = parseFloat(document.getElementById("lat_max").value);
  const lonMin = parseFloat(document.getElementById("lon_min").value);
  const lonMax = parseFloat(document.getElementById("lon_max").value);
  if ([latMin, latMax, lonMin, lonMax].some(v => isNaN(v))) {
    setProcessError("Please fill in all GPS bounds fields.");
    return;
  }

  // File
  const fileInput = document.getElementById("media-file");
  if (!fileInput.files[0]) {
    setProcessError("Please upload a video or image file.");
    return;
  }

  setProcessError("");
  showResults("queued", 0);
  document.getElementById("btn-process").disabled = true;

  const fd = new FormData();
  fd.append("file", fileInput.files[0]);
  fd.append("lat_min", latMin);
  fd.append("lat_max", latMax);
  fd.append("lon_min", lonMin);
  fd.append("lon_max", lonMax);
  fd.append("polygon", JSON.stringify(polygon));
  fd.append("tight", document.getElementById("opt-tight").checked ? "true" : "false");
  fd.append("bg_color", document.getElementById("opt-bg").value);

  try {
    const res = await fetch("/api/process", { method: "POST", body: fd });
    const data = await res.json();
    if (data.error) { setProcessError(data.error); showResults(null); return; }
    pollJob(data.job_id);
  } catch (e) {
    setProcessError("Upload failed: " + e.message);
    showResults(null);
    document.getElementById("btn-process").disabled = false;
  }
});

async function pollJob(jobId) {
  clearTimeout(pollTimer);
  try {
    const res = await fetch(`/api/status/${jobId}`);
    const job = await res.json();
    showResults(job.status, job.progress || 0, jobId, job.error);

    if (job.status === "done" || job.status === "error") {
      document.getElementById("btn-process").disabled = false;
      return;
    }
    pollTimer = setTimeout(() => pollJob(jobId), 800);
  } catch (e) {
    pollTimer = setTimeout(() => pollJob(jobId), 2000);
  }
}

// ------------------------------------------------------------------ //
// Results bar                                                         //
// ------------------------------------------------------------------ //
function showResults(status, progress = 0, jobId = null, errMsg = null) {
  const bar = document.getElementById("results-bar");
  if (!status) { bar.classList.remove("visible"); return; }

  bar.classList.add("visible");
  document.getElementById("progress-fill").style.width = progress + "%";
  document.getElementById("progress-pct").textContent = progress + "%";

  const badge = document.getElementById("status-badge");
  badge.className = `status-badge status-${status}`;
  badge.textContent = status;

  const dlBtn = document.getElementById("btn-download");
  if (status === "done" && jobId) {
    dlBtn.style.display = "inline-flex";
    dlBtn.onclick = () => { window.location = `/api/download/${jobId}`; };
  } else {
    dlBtn.style.display = "none";
  }

  const errEl = document.getElementById("results-error");
  errEl.textContent = errMsg ? `Error: ${errMsg}` : "";
}

function setProcessError(msg) {
  document.getElementById("process-error").textContent = msg;
}

// ------------------------------------------------------------------ //
// Map hint / badge helpers                                            //
// ------------------------------------------------------------------ //
function showHint(msg) {
  const el = document.getElementById("draw-hint");
  el.textContent = msg;
  el.classList.add("visible");
}
function hideHint() {
  document.getElementById("draw-hint").classList.remove("visible");
}
function showPtsBadge(n) {
  const el = document.getElementById("map-pts-badge");
  el.textContent = `${n} point${n !== 1 ? "s" : ""} added`;
  el.classList.add("visible");
}
function hidePtsBadge() {
  document.getElementById("map-pts-badge").classList.remove("visible");
}

// ------------------------------------------------------------------ //
// Utilities                                                           //
// ------------------------------------------------------------------ //
function escHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
