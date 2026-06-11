import re
import time
import requests
from flask import Flask, jsonify, Response

app = Flask(__name__)

BASE = "https://rest.citybus.gr/api/v1"
AGENCY = "112"
LANG = "el"
STATIC_TTL = 6 * 3600  # stops/lines/geometry/timetables change rarely

_token = {"value": None}
_cache = {}


def get_token(force=False):
    """The citybus site embeds a short-lived bearer token in its HTML."""
    if _token["value"] and not force:
        return _token["value"]
    try:
        html = requests.get("https://patra.citybus.gr/el/stops", timeout=8).text
        m = re.search(r"const token\s*=\s*['\"]([^'\"]+)['\"]", html)
        if m:
            _token["value"] = m.group(1)
    except Exception as e:
        print(f"[-] token harvest failed: {e}")
    return _token["value"]


def upstream(path, ttl=0):
    now = time.time()
    if ttl and path in _cache:
        expiry, data = _cache[path]
        if expiry > now:
            return data

    token = get_token()
    if not token:
        return {"error": "Could not obtain transit API token"}

    url = f"{BASE}/{path}"
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=8)
        if r.status_code == 401:
            token = get_token(force=True)
            if not token:
                return {"error": "Could not refresh transit API token"}
            r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=8)

        if r.status_code == 200:
            data = r.json()
        elif r.status_code == 404:
            data = []  # upstream returns 404 for "no data", not for bad routes
        else:
            return {"error": f"Transit API status {r.status_code}"}

        if ttl:
            _cache[path] = (now + ttl, data)
        return data
    except Exception as e:
        return {"error": str(e)}


@app.route("/api/stops")
def api_stops():
    return jsonify(upstream(f"{LANG}/{AGENCY}/stops", STATIC_TTL))


@app.route("/api/lines")
def api_lines():
    return jsonify(upstream(f"{LANG}/{AGENCY}/lines", STATIC_TTL))


@app.route("/api/stop/<code>/live")
def api_stop_live(code):
    return jsonify(upstream(f"{LANG}/{AGENCY}/stops/live/{code}"))


@app.route("/api/stop/<code>/trips/<int:day>")
def api_stop_trips(code, day):
    return jsonify(upstream(f"{LANG}/{AGENCY}/trips/stop/{code}/day/{day}", STATIC_TTL))


@app.route("/api/line/<code>/points")
def api_line_points(code):
    return jsonify(upstream(f"{AGENCY}/lines/{code}/points", STATIC_TTL))


@app.route("/api/route/<code>/sequence")
def api_route_sequence(code):
    return jsonify(upstream(f"{LANG}/{AGENCY}/routes/{code}/sequence", STATIC_TTL))


@app.route("/")
def home():
    return Response(HTML, mimetype="text/html")


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0c0e13">
<title>Patras Bus · Live</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0c0e13;
  --panel: rgba(16, 19, 26, .94);
  --panel-solid: #12151c;
  --card: #181c25;
  --card-hover: #1f2430;
  --border: rgba(255, 255, 255, .08);
  --text: #e8eaf0;
  --muted: #8b93a7;
  --accent: #34d399;
  --accent-dim: rgba(52, 211, 153, .14);
  --blue: #60a5fa;
  --danger: #f87171;
  --radius: 14px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  font-family: 'Inter', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  overflow: hidden;
}
#map { position: fixed; inset: 0; background: #0c0e13; }
.leaflet-container { font: inherit; }

/* ---------- floating panel ---------- */
.panel {
  position: fixed; top: 14px; left: 14px; bottom: 14px;
  width: 392px; max-width: calc(100vw - 28px);
  background: var(--panel);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border: 1px solid var(--border);
  border-radius: 18px;
  display: flex; flex-direction: column;
  z-index: 1000;
  box-shadow: 0 18px 50px rgba(0, 0, 0, .55);
  overflow: hidden;
}
.panel-head {
  padding: 16px 16px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.brand-row { display: flex; align-items: center; justify-content: space-between; }
.brand { font-size: 1.06rem; font-weight: 800; letter-spacing: -.02em; }
.brand .dot { color: var(--accent); }
.head-meta { display: flex; align-items: center; gap: 8px; font-size: .74rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.pulse-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); animation: pulse 1.6s infinite; display: none; }
.pulse-dot.on { display: inline-block; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(52,211,153,.5);} 70% { box-shadow: 0 0 0 7px rgba(52,211,153,0);} 100% { box-shadow: 0 0 0 0 rgba(52,211,153,0);} }

.search-row { margin-top: 12px; position: relative; }
.search-row input {
  width: 100%; padding: 10px 12px 10px 36px;
  background: var(--card); color: var(--text);
  border: 1px solid var(--border); border-radius: 10px;
  font: inherit; font-size: .88rem; outline: none;
}
.search-row input:focus { border-color: var(--accent); }
.search-row .ic { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); opacity: .55; font-size: .85rem; }

.tabs { display: flex; gap: 6px; margin-top: 12px; }
.tab {
  flex: 1; padding: 8px 0; text-align: center;
  font-size: .8rem; font-weight: 600; color: var(--muted);
  background: transparent; border: 1px solid transparent;
  border-radius: 9px; cursor: pointer; font-family: inherit;
}
.tab.active { color: var(--accent); background: var(--accent-dim); border-color: rgba(52, 211, 153, .25); }
.tab:hover:not(.active) { color: var(--text); background: var(--card); }

.panel-body { flex: 1; overflow-y: auto; padding: 12px; scrollbar-width: thin; scrollbar-color: #2a2f3c transparent; }
.panel-body::-webkit-scrollbar { width: 8px; }
.panel-body::-webkit-scrollbar-thumb { background: #2a2f3c; border-radius: 4px; }

/* ---------- cards ---------- */
.card {
  display: flex; align-items: center; gap: 12px;
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 11px 13px; margin-bottom: 8px;
  cursor: pointer; transition: background .12s, border-color .12s, transform .08s;
}
.card:hover { background: var(--card-hover); border-color: rgba(255, 255, 255, .15); }
.card:active { transform: scale(.985); }
.card-main { flex: 1; min-width: 0; }
.card-title { font-size: .875rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card-sub { font-size: .73rem; color: var(--muted); margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stop-ic { font-size: 1.05rem; opacity: .9; }
.fav-btn { background: none; border: none; cursor: pointer; font-size: 1.05rem; color: #3d4356; padding: 4px; font-family: inherit; }
.fav-btn.on { color: #fbbf24; }
.fav-btn:hover { transform: scale(1.15); }

.line-badge {
  min-width: 44px; padding: 5px 8px; border-radius: 8px;
  font-weight: 800; font-size: .82rem; text-align: center;
  border: 1.5px solid transparent; flex-shrink: 0; letter-spacing: .02em;
}
.eta-box { text-align: right; flex-shrink: 0; }
.eta-box b { font-size: 1.06rem; font-weight: 800; color: var(--accent); font-variant-numeric: tabular-nums; }
.eta-box b.due { color: var(--danger); animation: blink 1.2s infinite; }
@keyframes blink { 50% { opacity: .45; } }
.eta-box span { display: block; font-size: .64rem; color: var(--muted); margin-top: 2px; }

.section-note { font-size: .72rem; color: var(--muted); text-align: center; padding: 8px 0 4px; }
.empty {
  text-align: center; color: var(--muted); font-size: .83rem;
  padding: 34px 18px; line-height: 1.6;
}
.empty .big { font-size: 1.8rem; display: block; margin-bottom: 8px; }

/* ---------- detail views ---------- */
.detail-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.back-btn {
  background: var(--card); border: 1px solid var(--border); color: var(--text);
  border-radius: 9px; padding: 7px 11px; cursor: pointer; font-size: .8rem; font-family: inherit; flex-shrink: 0;
}
.back-btn:hover { background: var(--card-hover); }
.detail-title { font-size: .95rem; font-weight: 700; flex: 1; min-width: 0; line-height: 1.3; }
.detail-sub { font-size: .73rem; color: var(--muted); margin: 6px 0 12px; }
.subtabs { display: flex; gap: 6px; margin-bottom: 12px; }
.subtab {
  flex: 1; padding: 7px 0; font-size: .78rem; font-weight: 600; text-align: center;
  background: var(--card); color: var(--muted); border: 1px solid var(--border);
  border-radius: 9px; cursor: pointer; font-family: inherit;
}
.subtab.active { color: var(--text); border-color: var(--accent); background: var(--accent-dim); }

.day-row { display: flex; gap: 4px; margin-bottom: 10px; }
.day-chip {
  flex: 1; text-align: center; padding: 6px 0; font-size: .7rem; font-weight: 600;
  background: var(--card); color: var(--muted); border: 1px solid var(--border);
  border-radius: 8px; cursor: pointer; font-family: inherit;
}
.day-chip.active { color: var(--accent); border-color: var(--accent); }
.line-filter-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.lf-chip {
  padding: 4px 10px; font-size: .72rem; font-weight: 700; border-radius: 7px;
  cursor: pointer; border: 1.5px solid var(--border); background: var(--card); color: var(--muted);
  font-family: inherit;
}
.lf-chip.active { color: #fff; }

.tt-row { display: flex; gap: 10px; padding: 7px 4px; border-bottom: 1px solid var(--border); }
.tt-hour { width: 30px; font-weight: 800; font-size: .85rem; color: var(--muted); font-variant-numeric: tabular-nums; padding-top: 3px; }
.tt-chips { flex: 1; display: flex; flex-wrap: wrap; gap: 5px; }
.tt-chip {
  font-size: .76rem; font-weight: 600; padding: 3px 8px; border-radius: 6px;
  background: var(--card); border: 1.5px solid var(--border); font-variant-numeric: tabular-nums;
}
.tt-chip.next { border-color: var(--accent); color: var(--accent); font-weight: 800; }
.tt-chip.past { opacity: .38; }

.dir-row { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.dir-btn {
  padding: 8px 12px; text-align: left; font-size: .78rem; font-weight: 600;
  background: var(--card); color: var(--muted); border: 1px solid var(--border);
  border-radius: 9px; cursor: pointer; font-family: inherit;
}
.dir-btn.active { color: var(--text); border-color: var(--accent); background: var(--accent-dim); }
.seq-item { display: flex; align-items: center; gap: 10px; padding: 7px 6px; border-bottom: 1px solid var(--border); cursor: pointer; border-radius: 8px; }
.seq-item:hover { background: var(--card); }
.seq-num { width: 24px; height: 24px; border-radius: 50%; background: var(--card); border: 1px solid var(--border); font-size: .66rem; font-weight: 700; display: flex; align-items: center; justify-content: center; color: var(--muted); flex-shrink: 0; }
.seq-name { font-size: .8rem; flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.action-row { display: flex; gap: 8px; margin-bottom: 12px; }
.action-btn {
  flex: 1; padding: 8px 0; font-size: .76rem; font-weight: 600; text-align: center;
  background: var(--card); color: var(--text); border: 1px solid var(--border);
  border-radius: 9px; cursor: pointer; font-family: inherit;
}
.action-btn:hover { border-color: var(--accent); }

/* ---------- map markers ---------- */
.bus-marker { transition: transform 2s linear; }
.bus-pin {
  display: flex; flex-direction: column; align-items: center;
  filter: drop-shadow(0 3px 6px rgba(0, 0, 0, .6));
}
.bus-pin .pin-label {
  padding: 4px 8px; border-radius: 8px; font-weight: 800; font-size: 12px;
  font-family: 'Inter', sans-serif; border: 2px solid; white-space: nowrap;
}
.bus-pin .pin-tip { width: 0; height: 0; border: 5px solid transparent; border-top-width: 7px; border-bottom: none; margin-top: -1px; }
.stop-pulse { position: relative; }
.stop-pulse .ring {
  position: absolute; inset: -8px; border-radius: 50%;
  border: 2px solid var(--accent); animation: ringpulse 1.8s infinite;
}
@keyframes ringpulse { 0% { transform: scale(.55); opacity: 1; } 100% { transform: scale(1.35); opacity: 0; } }
.stop-pulse .core { width: 16px; height: 16px; border-radius: 50%; background: var(--accent); border: 3px solid #fff; box-shadow: 0 2px 8px rgba(0,0,0,.5); }
.user-dot { position: relative; }
.user-dot .halo { position: absolute; inset: -10px; border-radius: 50%; background: rgba(96, 165, 250, .25); animation: ringpulse 2.4s infinite; }
.user-dot .core { width: 14px; height: 14px; border-radius: 50%; background: var(--blue); border: 3px solid #fff; box-shadow: 0 2px 6px rgba(0,0,0,.5); }

.leaflet-popup-content-wrapper { background: var(--panel-solid); color: var(--text); border: 1px solid var(--border); border-radius: 12px; font-family: 'Inter', sans-serif; }
.leaflet-popup-tip { background: var(--panel-solid); }
.leaflet-popup-content { margin: 10px 14px; font-size: .8rem; line-height: 1.5; }
.leaflet-container a.leaflet-popup-close-button { color: var(--muted); }
.leaflet-tooltip {
  background: var(--panel-solid); color: var(--text); border: 1px solid var(--border);
  border-radius: 8px; font-family: 'Inter', sans-serif; font-size: .72rem; font-weight: 600;
  box-shadow: 0 4px 14px rgba(0,0,0,.4);
}
.leaflet-tooltip-top:before { border-top-color: var(--border); }
.leaflet-control-zoom a { background: var(--panel-solid) !important; color: var(--text) !important; border-color: var(--border) !important; }
.leaflet-control-attribution { background: rgba(12, 14, 19, .7) !important; color: #555e72 !important; font-size: .62rem !important; }
.leaflet-control-attribution a { color: #6b7489 !important; }

/* ---------- floating buttons & toast ---------- */
.locate-btn {
  position: fixed; right: 16px; bottom: 26px; z-index: 1000;
  width: 46px; height: 46px; border-radius: 50%;
  background: var(--panel-solid); border: 1px solid var(--border); color: var(--text);
  font-size: 1.15rem; cursor: pointer; box-shadow: 0 8px 22px rgba(0,0,0,.5);
}
.locate-btn:hover { border-color: var(--accent); }
.toast {
  position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%) translateY(80px);
  background: var(--panel-solid); border: 1px solid var(--border); color: var(--text);
  padding: 10px 18px; border-radius: 12px; font-size: .8rem; z-index: 2000;
  transition: transform .25s ease; box-shadow: 0 10px 30px rgba(0,0,0,.5); max-width: 86vw;
}
.toast.show { transform: translateX(-50%) translateY(0); }

/* ---------- mobile: bottom sheet ---------- */
@media (max-width: 640px) {
  .panel { top: auto; left: 0; right: 0; bottom: 0; width: 100%; max-width: 100%; height: 52vh; border-radius: 18px 18px 0 0; }
  .locate-btn { bottom: calc(52vh + 14px); }
  .toast { bottom: calc(52vh + 14px); }
}
</style>
</head>
<body>
<div id="map"></div>

<aside class="panel">
  <div class="panel-head">
    <div class="brand-row">
      <div class="brand">Patras Bus<span class="dot">·</span>Live</div>
      <div class="head-meta">
        <span class="pulse-dot" id="pulse-dot"></span>
        <span id="status-text"></span>
        <span id="clock"></span>
      </div>
    </div>
    <div class="search-row" id="search-row">
      <span class="ic">🔍</span>
      <input id="search-input" type="text" placeholder="Search stops or lines…" autocomplete="off">
    </div>
    <nav class="tabs" id="main-tabs">
      <button class="tab active" data-tab="nearby">🚏 Nearby</button>
      <button class="tab" data-tab="lines">🚌 Lines</button>
      <button class="tab" data-tab="saved">⭐ Saved</button>
    </nav>
  </div>
  <div class="panel-body" id="panel-body">
    <div class="empty"><span class="big">⏳</span>Loading network…</div>
  </div>
</aside>

<button class="locate-btn" id="locate-btn" title="My location">📍</button>
<div class="toast" id="toast"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
'use strict';
const PATRAS_CENTER = [38.2466, 21.7346];
const LIVE_REFRESH_MS = 10000;

// ---------- state ----------
let map, stopsLayer, routeLayer, stopHighlight, userMarker, userHalo;
let stops = [], stopsByCode = {}, lines = [], linesByCode = {};
let userPos = null;
let favorites = JSON.parse(localStorage.getItem('pb_favs') || '[]');
let mainTab = 'nearby';           // nearby | lines | saved
let view = 'list';                // list | stop | line
let selectedStop = null, selectedLine = null, activeRoute = null;
let stopSubTab = 'live';          // live | timetable
let ttDay = jsToApiDay(new Date().getDay());
let ttLineFilter = null;
let liveTimer = null, lastUpdate = null;
let busMarkers = {};
let searchQuery = '';
const pointsCache = {}, seqCache = {}, tripsCache = {};

const $body = document.getElementById('panel-body');
const $search = document.getElementById('search-input');

// ---------- helpers ----------
function esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function jsToApiDay(d) { return d === 0 ? 7 : d; }
function haversine(la1, lo1, la2, lo2) {
  const R = 6371000, r = Math.PI / 180;
  const dLa = (la2 - la1) * r, dLo = (lo2 - lo1) * r;
  const a = Math.sin(dLa / 2) ** 2 + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin(dLo / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
function fmtDist(m) { return m < 1000 ? Math.round(m) + ' m' : (m / 1000).toFixed(1) + ' km'; }
function walkMins(m) { return Math.max(1, Math.round(m / 78)); }
function badge(code, color, textColor, borderColor) {
  return `<span class="line-badge" style="background:${esc(color || '#2a2f3c')};color:${esc(textColor || '#fff')};border-color:${esc(borderColor || 'transparent')}">${esc(code)}</span>`;
}
function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove('show'), 3200);
}
async function getJSON(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (data && !Array.isArray(data) && data.error) throw new Error(data.error);
  return data;
}

// ---------- map ----------
function initMap() {
  map = L.map('map', { zoomControl: false, preferCanvas: true }).setView(PATRAS_CENTER, 14);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    maxZoom: 19
  }).addTo(map);
  stopsLayer = L.layerGroup();
  routeLayer = L.layerGroup().addTo(map);
  map.on('zoomend', syncStopsLayer);
}

function buildStopsLayer() {
  stops.forEach(s => {
    const m = L.circleMarker([s.latitude, s.longitude], {
      radius: 4, color: '#5a6379', weight: 1.5, fillColor: '#11141b', fillOpacity: .9
    });
    m.bindTooltip(esc(s.name), { direction: 'top', offset: [0, -4] });
    m.on('click', () => selectStop(s.code));
    stopsLayer.addLayer(m);
  });
  syncStopsLayer();
}
function syncStopsLayer() {
  if (map.getZoom() >= 15) { if (!map.hasLayer(stopsLayer)) map.addLayer(stopsLayer); }
  else if (map.hasLayer(stopsLayer)) map.removeLayer(stopsLayer);
}

function highlightStop(s) {
  if (stopHighlight) map.removeLayer(stopHighlight);
  stopHighlight = L.marker([s.latitude, s.longitude], {
    icon: L.divIcon({ className: '', html: '<div class="stop-pulse"><div class="ring"></div><div class="core"></div></div>', iconSize: [16, 16], iconAnchor: [8, 8] }),
    zIndexOffset: 500
  }).addTo(map).bindTooltip(esc(s.name), { direction: 'top', offset: [0, -10] });
}

function clearMapSelection() {
  if (stopHighlight) { map.removeLayer(stopHighlight); stopHighlight = null; }
  routeLayer.clearLayers();
  clearBuses();
}

// ---------- buses ----------
function etaText(v) {
  const secs = (v.departureMins || 0) * 60 + (v.departureSeconds || 0);
  if (secs <= 60) return 'now';
  return Math.round(secs / 60) + "'";
}
function updateBuses(vehicles) {
  const seen = new Set();
  vehicles.forEach(v => {
    const lat = parseFloat(v.latitude), lng = parseFloat(v.longitude);
    if (isNaN(lat) || isNaN(lng)) return;
    const id = v.vehicleCode || (v.lineCode + '_' + v.routeCode);
    seen.add(id);
    const tip = `${esc(v.lineCode)} ${esc(v.lineName)} · ${etaText(v)}`;
    if (busMarkers[id]) {
      busMarkers[id].setLatLng([lat, lng]);
      busMarkers[id].setTooltipContent(tip);
    } else {
      const icon = L.divIcon({
        className: 'bus-marker',
        html: `<div class="bus-pin"><div class="pin-label" style="background:${esc(v.lineColor || '#2a2f3c')};color:${esc(v.lineTextColor || '#fff')};border-color:${esc(v.borderColor || '#000')}">${esc(v.lineCode)}</div><div class="pin-tip" style="border-top-color:${esc(v.borderColor || v.lineColor || '#2a2f3c')}"></div></div>`,
        iconSize: [40, 30], iconAnchor: [20, 30]
      });
      const m = L.marker([lat, lng], { icon, zIndexOffset: 1000 }).addTo(map);
      m.bindTooltip(tip, { direction: 'top', offset: [0, -28] });
      m.on('click', () => drawRouteForVehicle(v));
      busMarkers[id] = m;
    }
  });
  for (const id in busMarkers) {
    if (!seen.has(id)) { map.removeLayer(busMarkers[id]); delete busMarkers[id]; }
  }
}
function clearBuses() {
  for (const id in busMarkers) map.removeLayer(busMarkers[id]);
  busMarkers = {};
}

async function drawRouteForVehicle(v) {
  try {
    const data = await getLinePoints(v.lineCode);
    const entry = data.find(p => p.routeCode === v.routeCode) || data[0];
    if (!entry) return;
    routeLayer.clearLayers();
    const latlngs = entry.routePoints.map(p => [parseFloat(p.latitude), parseFloat(p.longitude)]);
    L.polyline(latlngs, { color: v.lineColor === '#787878' ? '#34d399' : (v.lineColor || '#34d399'), weight: 4, opacity: .75 }).addTo(routeLayer);
    toast(`Route drawn: ${v.lineCode} ${v.routeName || v.lineName}`);
  } catch (e) { toast('Could not load route: ' + e.message); }
}
async function getLinePoints(lineCode) {
  if (!pointsCache[lineCode]) pointsCache[lineCode] = await getJSON(`/api/line/${encodeURIComponent(lineCode)}/points`);
  return pointsCache[lineCode];
}

// ---------- live polling ----------
function startLive() {
  stopLive();
  document.getElementById('pulse-dot').classList.add('on');
  fetchLive();
  liveTimer = setInterval(fetchLive, LIVE_REFRESH_MS);
}
function stopLive() {
  if (liveTimer) { clearInterval(liveTimer); liveTimer = null; }
  document.getElementById('pulse-dot').classList.remove('on');
  document.getElementById('status-text').textContent = '';
}
async function fetchLive() {
  if (!selectedStop) return;
  try {
    const data = await getJSON(`/api/stop/${encodeURIComponent(selectedStop.code)}/live`);
    const vehicles = (data && data.vehicles) || [];
    lastUpdate = Date.now();
    updateBuses(vehicles);
    if (view === 'stop' && stopSubTab === 'live') renderLiveList(vehicles);
  } catch (e) {
    if (view === 'stop' && stopSubTab === 'live') {
      $body.querySelector('#live-list')?.replaceChildren();
      toast('Live feed error: ' + e.message);
    }
  }
}

// ---------- views ----------
function setMainTab(tab) {
  mainTab = tab;
  view = 'list';
  selectedStop = null; selectedLine = null;
  stopLive();
  clearMapSelection();
  document.querySelectorAll('#main-tabs .tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  renderList();
}

function renderList() {
  document.getElementById('search-row').style.display = '';
  if (mainTab === 'nearby') renderNearby();
  else if (mainTab === 'lines') renderLines();
  else renderSaved();
}

function stopCardHtml(s) {
  const fav = favorites.includes(s.code);
  let sub = '#' + esc(s.code);
  if (userPos) {
    const d = haversine(userPos.lat, userPos.lng, s.latitude, s.longitude);
    sub += ` · ${fmtDist(d)} · 🚶 ${walkMins(d)} min`;
  }
  if (s.lineCodes && s.lineCodes.length) sub += ' · lines ' + s.lineCodes.slice(0, 4).map(esc).join(', ') + (s.lineCodes.length > 4 ? '…' : '');
  return `<div class="card stop-card" data-code="${esc(s.code)}">
    <div class="stop-ic">🚏</div>
    <div class="card-main"><div class="card-title">${esc(s.name)}</div><div class="card-sub">${sub}</div></div>
    <button class="fav-btn ${fav ? 'on' : ''}" data-fav="${esc(s.code)}" title="Save stop">${fav ? '★' : '☆'}</button>
  </div>`;
}

function renderNearby() {
  let list = stops;
  const q = searchQuery.trim().toLowerCase();
  if (q) list = list.filter(s => s.name.toLowerCase().includes(q) || s.code.includes(q));
  if (userPos) {
    list = [...list].sort((a, b) =>
      haversine(userPos.lat, userPos.lng, a.latitude, a.longitude) -
      haversine(userPos.lat, userPos.lng, b.latitude, b.longitude));
  } else {
    list = [...list].sort((a, b) => a.name.localeCompare(b.name, 'el'));
  }
  const shown = list.slice(0, 60);
  let html = shown.map(stopCardHtml).join('');
  if (!shown.length) html = `<div class="empty"><span class="big">🔍</span>No stops match “${esc(searchQuery)}”.</div>`;
  else if (list.length > shown.length) html += `<div class="section-note">Showing ${shown.length} of ${list.length} stops — search to narrow down.</div>`;
  if (!userPos && !q) html = `<div class="section-note">📍 Tap the locate button to sort stops by distance.</div>` + html;
  $body.innerHTML = html;
  bindStopCards();
}

function renderLines() {
  const q = searchQuery.trim().toLowerCase();
  let list = lines;
  if (q) list = list.filter(l => l.code.toLowerCase().includes(q) || l.name.toLowerCase().includes(q));
  let html = list.map(l => `
    <div class="card line-card" data-line="${esc(l.code)}">
      ${badge(l.code, l.color, l.textColor, l.borderColor)}
      <div class="card-main"><div class="card-title">${esc(l.name)}</div><div class="card-sub">${l.routes.length} direction${l.routes.length !== 1 ? 's' : ''}</div></div>
      <div style="color:var(--muted);font-size:.9rem">›</div>
    </div>`).join('');
  if (!list.length) html = `<div class="empty"><span class="big">🚌</span>No lines match “${esc(searchQuery)}”.</div>`;
  $body.innerHTML = html;
  $body.querySelectorAll('.line-card').forEach(el => el.addEventListener('click', () => selectLine(el.dataset.line)));
}

function renderSaved() {
  const savedStops = favorites.map(c => stopsByCode[c]).filter(Boolean);
  const q = searchQuery.trim().toLowerCase();
  let list = q ? savedStops.filter(s => s.name.toLowerCase().includes(q) || s.code.includes(q)) : savedStops;
  if (!list.length) {
    $body.innerHTML = `<div class="empty"><span class="big">⭐</span>No saved stops yet.<br>Tap the star on any stop to keep it here.</div>`;
    return;
  }
  $body.innerHTML = list.map(stopCardHtml).join('');
  bindStopCards();
}

function bindStopCards() {
  $body.querySelectorAll('.stop-card').forEach(el =>
    el.addEventListener('click', () => selectStop(el.dataset.code)));
  $body.querySelectorAll('.fav-btn').forEach(el =>
    el.addEventListener('click', e => { e.stopPropagation(); toggleFav(el.dataset.fav); }));
}

function toggleFav(code) {
  const i = favorites.indexOf(code);
  if (i >= 0) favorites.splice(i, 1); else favorites.push(code);
  localStorage.setItem('pb_favs', JSON.stringify(favorites));
  if (view === 'stop') renderStopDetail(); else renderList();
}

// ---------- stop detail ----------
function selectStop(code) {
  const s = stopsByCode[code];
  if (!s) { toast('Unknown stop ' + code); return; }
  selectedStop = s; selectedLine = null;
  view = 'stop'; stopSubTab = 'live';
  ttDay = jsToApiDay(new Date().getDay());
  ttLineFilter = null;
  location.hash = 'stop=' + encodeURIComponent(code);
  clearMapSelection();
  highlightStop(s);
  const pts = [[s.latitude, s.longitude]];
  if (userPos) pts.push([userPos.lat, userPos.lng]);
  if (pts.length > 1) map.fitBounds(pts, { padding: [70, 70], maxZoom: 16 });
  else map.flyTo([s.latitude, s.longitude], 16, { duration: .6 });
  renderStopDetail();
  startLive();
}

function renderStopDetail() {
  const s = selectedStop;
  const fav = favorites.includes(s.code);
  let meta = '#' + esc(s.code);
  if (userPos) {
    const d = haversine(userPos.lat, userPos.lng, s.latitude, s.longitude);
    meta += ` · ${fmtDist(d)} away · 🚶 ${walkMins(d)} min walk`;
  }
  document.getElementById('search-row').style.display = 'none';
  $body.innerHTML = `
    <div class="detail-head">
      <button class="back-btn" id="back-btn">‹ Back</button>
      <div class="detail-title">${esc(s.name)}</div>
      <button class="fav-btn ${fav ? 'on' : ''}" id="detail-fav">${fav ? '★' : '☆'}</button>
    </div>
    <div class="detail-sub">${meta}</div>
    <div class="action-row">
      <button class="action-btn" id="fit-btn">🎯 Fit map</button>
      <button class="action-btn" id="share-btn">🔗 Copy link</button>
    </div>
    <div class="subtabs">
      <button class="subtab ${stopSubTab === 'live' ? 'active' : ''}" data-st="live">⚡ Live</button>
      <button class="subtab ${stopSubTab === 'timetable' ? 'active' : ''}" data-st="timetable">🕒 Timetable</button>
    </div>
    <div id="stop-content"><div class="empty"><span class="big">⏳</span>Loading…</div></div>`;
  document.getElementById('back-btn').addEventListener('click', goBack);
  document.getElementById('detail-fav').addEventListener('click', () => toggleFav(s.code));
  document.getElementById('fit-btn').addEventListener('click', fitToStopAndBuses);
  document.getElementById('share-btn').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(location.href); toast('Link copied'); }
    catch { toast(location.href); }
  });
  $body.querySelectorAll('.subtab').forEach(b => b.addEventListener('click', () => {
    stopSubTab = b.dataset.st;
    $body.querySelectorAll('.subtab').forEach(x => x.classList.toggle('active', x.dataset.st === stopSubTab));
    if (stopSubTab === 'live') fetchLive(); else renderTimetable();
  }));
  if (stopSubTab === 'live') fetchLive(); else renderTimetable();
}

function fitToStopAndBuses() {
  const pts = [[selectedStop.latitude, selectedStop.longitude]];
  for (const id in busMarkers) { const ll = busMarkers[id].getLatLng(); pts.push([ll.lat, ll.lng]); }
  if (userPos) pts.push([userPos.lat, userPos.lng]);
  map.fitBounds(pts, { padding: [70, 70], maxZoom: 16 });
}

function renderLiveList(vehicles) {
  const c = document.getElementById('stop-content');
  if (!c) return;
  const upd = lastUpdate ? new Date(lastUpdate).toLocaleTimeString('en-GB') : '—';
  if (!vehicles.length) {
    c.innerHTML = `<div class="empty"><span class="big">🌙</span>No buses approaching in the next ~30 minutes.<br><span style="font-size:.72rem">Check the timetable for scheduled departures · updated ${upd}</span></div>`;
    return;
  }
  const sorted = [...vehicles].sort((a, b) =>
    ((a.departureMins || 0) * 60 + (a.departureSeconds || 0)) - ((b.departureMins || 0) * 60 + (b.departureSeconds || 0)));
  c.innerHTML = `<div id="live-list">` + sorted.map(v => {
    const eta = etaText(v);
    const hasGps = !isNaN(parseFloat(v.latitude)) && !isNaN(parseFloat(v.longitude));
    return `<div class="card live-card" data-veh="${esc(v.vehicleCode || '')}">
      ${badge(v.lineCode, v.lineColor, v.lineTextColor, v.borderColor)}
      <div class="card-main">
        <div class="card-title">${esc(v.lineName)}</div>
        <div class="card-sub">${esc(v.routeName)}</div>
      </div>
      <div class="eta-box"><b class="${eta === 'now' ? 'due' : ''}">${eta}</b><span>${hasGps ? '🛰 on map' : 'no GPS'}</span></div>
    </div>`;
  }).join('') + `</div><div class="section-note">Auto-refresh every 10 s · updated ${upd}</div>`;
  c.querySelectorAll('.live-card').forEach(el => el.addEventListener('click', () => {
    const id = el.dataset.veh;
    const m = busMarkers[id];
    const v = sorted.find(x => (x.vehicleCode || '') === id);
    if (m) { map.flyTo(m.getLatLng(), 16, { duration: .5 }); m.openTooltip(); }
    if (v) drawRouteForVehicle(v);
  }));
}

// ---------- timetable ----------
async function renderTimetable() {
  const c = document.getElementById('stop-content');
  if (!c) return;
  const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const dayRow = `<div class="day-row">` + dayNames.map((n, i) =>
    `<button class="day-chip ${ttDay === i + 1 ? 'active' : ''}" data-day="${i + 1}">${n}</button>`).join('') + `</div>`;
  c.innerHTML = dayRow + `<div id="tt-content"><div class="empty"><span class="big">⏳</span>Loading timetable…</div></div>`;
  c.querySelectorAll('.day-chip').forEach(b => b.addEventListener('click', () => { ttDay = +b.dataset.day; renderTimetable(); }));

  const key = selectedStop.code + ':' + ttDay;
  try {
    if (!tripsCache[key]) tripsCache[key] = await getJSON(`/api/stop/${encodeURIComponent(selectedStop.code)}/trips/${ttDay}`);
    const trips = tripsCache[key];
    const tc = document.getElementById('tt-content');
    if (!tc) return;
    if (!trips.length) { tc.innerHTML = `<div class="empty"><span class="big">🗓</span>No scheduled departures on ${dayNames[ttDay - 1]}.</div>`; return; }

    const lineCodes = [...new Set(trips.map(t => t.lineCode))];
    let filterRow = '';
    if (lineCodes.length > 1) {
      filterRow = `<div class="line-filter-row">
        <button class="lf-chip ${!ttLineFilter ? 'active' : ''}" data-lf="" style="${!ttLineFilter ? 'background:#2a2f3c;border-color:#3d4356' : ''}">All</button>` +
        lineCodes.map(lc => {
          const t = trips.find(x => x.lineCode === lc);
          const on = ttLineFilter === lc;
          return `<button class="lf-chip ${on ? 'active' : ''}" data-lf="${esc(lc)}" style="${on ? `background:${esc(t.lineColor)};border-color:${esc(t.lineColor)}` : ''}">${esc(lc)}</button>`;
        }).join('') + `</div>`;
    }

    const visible = ttLineFilter ? trips.filter(t => t.lineCode === ttLineFilter) : trips;
    const now = new Date();
    const isToday = ttDay === jsToApiDay(now.getDay());
    const nowMins = now.getHours() * 60 + now.getMinutes();
    let nextMarked = false;
    const byHour = {};
    visible.forEach(t => { (byHour[t.tripTimeHour] = byHour[t.tripTimeHour] || []).push(t); });
    const hours = Object.keys(byHour).map(Number).sort((a, b) => a - b);
    const rows = hours.map(h => {
      const chips = byHour[h]
        .sort((a, b) => a.tripTimeMinute - b.tripTimeMinute)
        .map(t => {
          const tMins = t.tripTimeHour * 60 + t.tripTimeMinute;
          let cls = '';
          if (isToday && tMins < nowMins) cls = 'past';
          else if (isToday && !nextMarked) { cls = 'next'; nextMarked = true; }
          return `<span class="tt-chip ${cls}" style="border-left:3px solid ${esc(t.lineColor || '#3d4356')}" title="${esc(t.lineCode)} ${esc(t.routeName)}">${String(t.tripTimeMinute).padStart(2, '0')}</span>`;
        }).join('');
      return `<div class="tt-row"><div class="tt-hour">${String(h).padStart(2, '0')}</div><div class="tt-chips">${chips}</div></div>`;
    }).join('');
    tc.innerHTML = filterRow + rows + `<div class="section-note">Minutes past each hour · ${visible.length} departures</div>`;
    tc.querySelectorAll('.lf-chip').forEach(b => b.addEventListener('click', () => { ttLineFilter = b.dataset.lf || null; renderTimetable(); }));
  } catch (e) {
    const tc = document.getElementById('tt-content');
    if (tc) tc.innerHTML = `<div class="empty"><span class="big">⚠️</span>${esc(e.message)}</div>`;
  }
}

// ---------- line detail ----------
async function selectLine(code) {
  const l = linesByCode[code];
  if (!l) return;
  selectedLine = l; selectedStop = null;
  view = 'line';
  stopLive();
  clearMapSelection();
  location.hash = 'line=' + encodeURIComponent(code);
  activeRoute = l.routes[0] ? l.routes[0].code : null;
  renderLineDetail();
}

async function renderLineDetail() {
  const l = selectedLine;
  document.getElementById('search-row').style.display = 'none';
  const dirBtns = l.routes.map(r =>
    `<button class="dir-btn ${activeRoute === r.code ? 'active' : ''}" data-route="${esc(r.code)}">↦ ${esc(r.name)}</button>`).join('');
  $body.innerHTML = `
    <div class="detail-head">
      <button class="back-btn" id="back-btn">‹ Back</button>
      ${badge(l.code, l.color, l.textColor, l.borderColor)}
      <div class="detail-title">${esc(l.name)}</div>
    </div>
    <div class="detail-sub">${l.routes.length} direction${l.routes.length !== 1 ? 's' : ''} · live positions appear when you open a stop</div>
    <div class="dir-row">${dirBtns}</div>
    <div id="line-content"><div class="empty"><span class="big">⏳</span>Loading route…</div></div>`;
  document.getElementById('back-btn').addEventListener('click', goBack);
  $body.querySelectorAll('.dir-btn').forEach(b => b.addEventListener('click', () => {
    activeRoute = b.dataset.route;
    renderLineDetail();
  }));
  await drawLineRoute();
}

async function drawLineRoute() {
  const l = selectedLine;
  const c = document.getElementById('line-content');
  try {
    const [points, seq] = await Promise.all([
      getLinePoints(l.code),
      activeRoute ? getRouteSeq(activeRoute) : Promise.resolve([])
    ]);
    if (view !== 'line' || selectedLine !== l) return;
    routeLayer.clearLayers();
    const entry = points.find(p => p.routeCode === activeRoute) || points[0];
    const color = l.color === '#787878' ? '#34d399' : (l.color || '#34d399');
    if (entry && entry.routePoints.length) {
      const latlngs = entry.routePoints.map(p => [parseFloat(p.latitude), parseFloat(p.longitude)]);
      L.polyline(latlngs, { color: '#0c0e13', weight: 8, opacity: .8 }).addTo(routeLayer);
      L.polyline(latlngs, { color, weight: 4, opacity: .95 }).addTo(routeLayer);
      map.fitBounds(latlngs, { padding: [60, 60] });
    }
    const items = seq.map(x => ({ ...x, stop: stopsByCode[x.code] })).filter(x => x.stop);
    items.forEach(x => {
      L.circleMarker([x.stop.latitude, x.stop.longitude], {
        radius: 5, color, weight: 2, fillColor: '#0c0e13', fillOpacity: 1
      }).bindTooltip(esc(x.stop.name), { direction: 'top', offset: [0, -4] })
        .on('click', () => selectStop(x.stop.code))
        .addTo(routeLayer);
    });
    if (!c) return;
    c.innerHTML = items.length
      ? items.map(x => `<div class="seq-item" data-code="${esc(x.stop.code)}">
            <div class="seq-num" style="border-color:${color};color:${color}">${x.sequence}</div>
            <div class="seq-name">${esc(x.stop.name)}</div>
            <div style="color:var(--muted);font-size:.85rem">›</div>
          </div>`).join('')
      : `<div class="empty">No stop sequence available for this direction.</div>`;
    c.querySelectorAll('.seq-item').forEach(el => el.addEventListener('click', () => selectStop(el.dataset.code)));
  } catch (e) {
    if (c) c.innerHTML = `<div class="empty"><span class="big">⚠️</span>${esc(e.message)}</div>`;
  }
}
async function getRouteSeq(routeCode) {
  if (!seqCache[routeCode]) seqCache[routeCode] = await getJSON(`/api/route/${encodeURIComponent(routeCode)}/sequence`);
  return seqCache[routeCode];
}

// ---------- navigation ----------
function goBack() {
  view = 'list';
  selectedStop = null; selectedLine = null;
  stopLive();
  clearMapSelection();
  history.replaceState(null, '', location.pathname);
  renderList();
}

// ---------- geolocation ----------
function locate(showErrors) {
  if (!navigator.geolocation) { if (showErrors) toast('Geolocation is not supported by this browser'); return; }
  navigator.geolocation.getCurrentPosition(pos => {
    userPos = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    if (!userMarker) {
      userMarker = L.marker([userPos.lat, userPos.lng], {
        icon: L.divIcon({ className: '', html: '<div class="user-dot"><div class="halo"></div><div class="core"></div></div>', iconSize: [14, 14], iconAnchor: [7, 7] }),
        zIndexOffset: 800
      }).addTo(map).bindTooltip('You are here', { direction: 'top', offset: [0, -10] });
    } else userMarker.setLatLng([userPos.lat, userPos.lng]);
    if (userHalo) map.removeLayer(userHalo);
    userHalo = L.circle([userPos.lat, userPos.lng], { radius: pos.coords.accuracy, color: '#60a5fa', weight: 1, opacity: .3, fillOpacity: .06 }).addTo(map);
    if (showErrors) map.flyTo([userPos.lat, userPos.lng], 15, { duration: .6 });
    if (view === 'list') renderList();
    else if (view === 'stop') renderStopDetail();
  }, err => {
    if (showErrors) toast('Location unavailable: ' + err.message);
  }, { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 });
}

// ---------- boot ----------
async function boot() {
  initMap();
  setInterval(() => {
    document.getElementById('clock').textContent = new Date().toLocaleTimeString('en-GB');
    if (lastUpdate && liveTimer) {
      document.getElementById('status-text').textContent = `live · ${Math.round((Date.now() - lastUpdate) / 1000)}s ago`;
    }
  }, 1000);

  document.querySelectorAll('#main-tabs .tab').forEach(b =>
    b.addEventListener('click', () => setMainTab(b.dataset.tab)));
  $search.addEventListener('input', () => { searchQuery = $search.value; if (view === 'list') renderList(); });
  document.getElementById('locate-btn').addEventListener('click', () => locate(true));
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && view !== 'list') goBack(); });

  try {
    const [stopsData, linesData] = await Promise.all([getJSON('/api/stops'), getJSON('/api/lines')]);
    stops = stopsData;
    lines = linesData;
    stops.forEach(s => { stopsByCode[s.code] = s; });
    lines.forEach(l => { linesByCode[l.code] = l; });
    buildStopsLayer();
    renderList();
    locate(false);

    const h = location.hash.slice(1);
    const mStop = h.match(/^stop=(.+)$/), mLine = h.match(/^line=(.+)$/);
    if (mStop) selectStop(decodeURIComponent(mStop[1]));
    else if (mLine) { setMainTab('lines'); selectLine(decodeURIComponent(mLine[1])); }
  } catch (e) {
    $body.innerHTML = `<div class="empty"><span class="big">⚠️</span>Could not load the bus network.<br>${esc(e.message)}<br><br><button class="back-btn" onclick="location.reload()">↻ Retry</button></div>`;
  }
}
boot();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True, port=5000)
