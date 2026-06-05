import re
import requests
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# Global persistent session and token memory cache to stop rate-limiting
SESSION_TOKEN = None

def get_cached_token(force_refresh=False):
    global SESSION_TOKEN
    if SESSION_TOKEN and not force_refresh:
        return SESSION_TOKEN
    
    try:
        # Flexible quote regex pattern to reliably intercept the security token
        html_res = requests.get("https://patra.citybus.gr/el/stops", timeout=8)
        match = re.search(r"const token\s*=\s*['\"]([^'\"]+)['\"]", html_res.text)
        if match:
            SESSION_TOKEN = match.group(1)
            return SESSION_TOKEN
    except Exception as e:
        print(f"[-] Token harvest failure: {e}")
    return SESSION_TOKEN

def fetch_transit_api(endpoint_url):
    token = get_cached_token()
    if not token:
        return {"error": "Authentication token missing from cache"}
        
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(endpoint_url, headers=headers, timeout=8)
        
        # If the cached token expired, force-refresh it once and retry the call
        if res.status_code == 401:
            token = get_cached_token(force_refresh=True)
            if token:
                headers = {"Authorization": f"Bearer {token}"}
                res = requests.get(endpoint_url, headers=headers, timeout=8)
                
        if res.status_code == 200:
            return res.json()
        else:
            return {"error": f"Transit API responded with status code {res.status_code}"}
    except Exception as e:
        return {"error": str(e)}


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📡 Patras CityBus Tracker (Fail-Safe Matrix)</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        :root {
            --bg: #0f0f11;
            --surface: #16161a;
            --surface-hover: #22222a;
            --text: #e1e1e6;
            --primary: #4ea8de;
            --accent: #00b37e;
            --danger: #f75a68;
            --border: #29292e;
        }
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 15px;
            box-sizing: border-box;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 10px;
        }
        h1 { margin: 0; font-size: 1.4rem; color: var(--primary); }
        .main-layout {
            display: grid;
            grid-template-columns: 380px 1fr;
            gap: 15px;
            flex-grow: 1;
            min-height: 0;
        }
        @media (max-width: 900px) {
            .main-layout { grid-template-columns: 1fr; }
        }
        .sidebar {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .tabs {
            display: flex;
            background: #121214;
            border-bottom: 1px solid var(--border);
        }
        .tab-btn {
            flex: 1;
            background: none;
            border: none;
            color: #8d8d99;
            padding: 12px;
            cursor: pointer;
            font-weight: bold;
            font-size: 0.9rem;
        }
        .tab-btn.active {
            color: var(--primary);
            border-bottom: 2px solid var(--primary);
            background: var(--surface);
        }
        .search-box { padding: 10px; border-bottom: 1px solid var(--border); }
        .search-box input {
            width: 100%; padding: 10px; background: #121214;
            border: 1px solid var(--border); color: white; border-radius: 6px; box-sizing: border-box;
        }
        .list-viewport { flex-grow: 1; overflow-y: auto; padding: 10px; }
        .item-card {
            background: #1c1c22; border: 1px solid var(--border);
            padding: 12px; border-radius: 6px; margin-bottom: 8px; cursor: pointer;
        }
        .item-card:hover { border-color: var(--primary); background: var(--surface-hover); }
        .item-card.selected-bus { border-color: var(--accent); background: #142520; }
        .item-title { font-weight: bold; color: #fff; font-size: 0.95rem; }
        .item-sub { color: #8d8d99; font-size: 0.8rem; margin-top: 4px; display: flex; justify-content: space-between; }
        .map-window {
            background: var(--surface); border: 1px solid var(--border);
            border-radius: 8px; display: flex; flex-direction: column; overflow: hidden; position: relative;
        }
        .map-bar {
            background: #121214; padding: 10px 15px; border-bottom: 1px solid var(--border);
            font-size: 0.85rem; display: flex; justify-content: space-between; align-items: center;
        }
        #map { flex-grow: 1; width: 100%; background: #111; }
        .badge-live { background: #143224; color: var(--accent); padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.75rem; display: inline-flex; align-items: center; gap: 4px;}
        .badge-pulse { width: 6px; height: 6px; background: var(--accent); border-radius: 50%; display: inline-block; animation: blink 1.2s infinite; }
        .badge-gps-status { background: #1b263b; color: #5c9ead; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }
        .badge-time { color: var(--primary); font-weight: bold; font-size: 1.05rem; }
        .loader { text-align: center; color: #8d8d99; padding: 20px; font-style: italic; }
        .empty-prompt { color: #8d8d99; font-size: 0.9rem; text-align: center; padding: 30px 10px; }
        @keyframes blink { 0% { opacity: 0.3; } 50% { opacity: 1; } 100% { opacity: 0.3; } }
    </style>
</head>
<body>

    <header>
        <div>
            <h1>📡 Patras CityBus System Live Monitor</h1>
            <div style="color: #8d8d99; font-size: 0.8rem; margin-top: 2px;">Protected Token Cache Engine & Distance-Sorted Navigation</div>
        </div>
        <div style="display: flex; gap: 10px; align-items: center;">
            <div id="gps-status" class="badge-gps-status">GPS: Pending Permission</div>
            <div id="radar-pulse" style="font-size: 0.85rem; color: #8d8d99; display:none;"><span class="badge-pulse"></span> Network Loop Active</div>
        </div>
    </header>

    <div class="main-layout">
        <div class="sidebar">
            <div class="tabs">
                <button id="tab-stops" class="tab-btn active" onclick="switchTab('stops')">🚏 Bus Stops</button>
                <button id="tab-arrivals" class="tab-btn" onclick="switchTab('arrivals')">⏱️ Live Arrivals</button>
            </div>
            <div class="search-box" id="sidebar-search-container">
                <input type="text" id="search-input" placeholder="Search stops by name or ID...">
            </div>
            <div id="list-viewport" class="list-viewport">
                <div class="loader">Initializing components...</div>
            </div>
        </div>
        
        <div class="map-window">
            <div class="map-bar">
                <div>🎯 SCOPE: <span id="map-scope-title" style="color: var(--primary); font-weight: bold;">Overview Map</span></div>
                <div id="map-stats-badge" class="badge-live">Ready</div>
            </div>
            <div id="map"></div>
        </div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        let mapInstance = null;
        let networkStopsCache = [];
        let activeTab = 'stops';
        let currentSelectedStop = null;
        let trackedVehicleId = null;
        let trackingInterval = null;
        
        // Map Layers
        let stopMarkerLayer = null;
        let busMarkerLayer = null;
        let userLocationLayer = null;

        // User Geolocation Coordinates
        let userCoordinates = null;

        function autoExtract(obj, searchKeys, fallback = "N/A") {
            if (!obj) return fallback;
            for (let k in obj) {
                if (searchKeys.some(sk => k.toLowerCase().includes(sk))) return obj[k];
            }
            return fallback;
        }

        function safeExtractArray(inputData) {
            if (Array.isArray(inputData)) return inputData;
            if (inputData && typeof inputData === 'object') {
                if (inputData.error) return [];
                for (let key in inputData) {
                    if (Array.isArray(inputData[key])) return inputData[key];
                }
            }
            return [];
        }

        function matchVehicleIds(id1, id2) {
            if (!id1 || !id2 || id1 === "N/A" || id2 === "N/A") return false;
            let s1 = String(id1).toLowerCase();
            let s2 = String(id2).toLowerCase();
            if (s1 === s2) return true;
            if (s1.includes('_') && s1.split('_').includes(s2)) return true;
            if (s2.includes('_') && s2.split('_').includes(s1)) return true;
            return false;
        }

        // Haversine Formula for distance tracking
        function calculateDistance(lat1, lon1, lat2, lon2) {
            if (!lat1 || !lon1 || !lat2 || !lon2) return null;
            const R = 6371; // Earth's radius in kilometers
            const dLat = (lat2 - lat1) * Math.PI / 180;
            const dLon = (lon2 - lon1) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon/2) * Math.sin(dLon/2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            return R * c; // returns distance in km
        }

        function initMap() {
            mapInstance = L.map('map', { attributionControl: false }).setView([38.2466, 21.7346], 13);
            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { maxZoom: 19 }).addTo(mapInstance);
            
            // Request user location right away
            requestUserLocation();
        }

        function requestUserLocation() {
            if (!navigator.geolocation) {
                document.getElementById('gps-status').innerText = "GPS: Not Supported";
                document.getElementById('gps-status').style.background = "#3a2222";
                return;
            }

            navigator.geolocation.getCurrentPosition(
                (position) => {
                    userCoordinates = {
                        lat: position.coords.latitude,
                        lng: position.coords.longitude
                    };
                    document.getElementById('gps-status').innerText = "GPS: Connected";
                    document.getElementById('gps-status').style.background = "#143224";
                    document.getElementById('gps-status').style.color = "var(--accent)";

                    // Plot user location on the map
                    updateUserMapMarker();

                    // resort list if cache is already loaded
                    if (networkStopsCache.length > 0) {
                        sortAndRenderStops();
                    }
                },
                (error) => {
                    console.warn(`Geolocation error: ${error.message}`);
                    document.getElementById('gps-status').innerText = "GPS: Denied/Failed";
                    document.getElementById('gps-status').style.background = "#3a2222";
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        }

        function updateUserMapMarker() {
            if (!userCoordinates || !mapInstance) return;

            if (userLocationLayer) {
                userLocationLayer.setLatLng([userCoordinates.lat, userCoordinates.lng]);
            } else {
                // Distinct neon-blue pulsing style for your location tracker
                userLocationLayer = L.circleMarker([userCoordinates.lat, userCoordinates.lng], {
                    radius: 8, color: '#007att', fillColor: '#4ea8de', fillOpacity: 0.9, weight: 3
                }).addTo(mapInstance).bindPopup("<b>📍 Your Location</b>");
            }
        }

        function switchTab(tabId) {
            activeTab = tabId;
            document.getElementById('tab-stops').className = `tab-btn ${tabId === 'stops' ? 'active' : ''}`;
            document.getElementById('tab-arrivals').className = `tab-btn ${tabId === 'arrivals' ? 'active' : ''}`;
            
            const searchBox = document.getElementById('sidebar-search-container');
            if (tabId === 'stops') {
                searchBox.style.display = 'block';
                sortAndRenderStops();
                stopTrackingPulse();
            } else {
                searchBox.style.display = 'none';
                renderArrivalsStream();
            }
        }

        async function loadStopsIndex() {
            try {
                const res = await fetch('/api/stops');
                const rawData = await res.json();
                
                if (rawData && rawData.error) throw new Error(rawData.error);
                let arrayPayload = safeExtractArray(rawData);

                networkStopsCache = arrayPayload.map(item => ({
                    id: autoExtract(item, ['id', 'code']),
                    name: autoExtract(item, ['descr', 'name', 'title']),
                    lat: parseFloat(autoExtract(item, ['lat', 'y'])),
                    lng: parseFloat(autoExtract(item, ['lng', 'lon', 'x'])),
                    raw: item
                }));

                sortAndRenderStops();
            } catch (e) {
                document.getElementById('list-viewport').innerHTML = `<div class="empty-prompt" style="color:var(--danger)">Failed to synchronize transit stations: ${e.message}</div>`;
            }
        }

        function sortAndRenderStops() {
            let processedStops = [...networkStopsCache];

            // Compute relative distance if user location data exists
            if (userCoordinates) {
                processedStops.forEach(stop => {
                    stop.distance = calculateDistance(userCoordinates.lat, userCoordinates.lng, stop.lat, stop.lng);
                });
                // Closest stops first
                processedStops.sort((a, b) => (a.distance || Infinity) - (b.distance || Infinity));
            }

            const query = document.getElementById('search-input').value.toLowerCase().trim();
            if (query) {
                processedStops = processedStops.filter(s => s.name.toLowerCase().includes(query) || s.id.toString().includes(query));
            }

            renderStops(processedStops);
        }

        function renderStops(stopsList) {
            const viewport = document.getElementById('list-viewport');
            viewport.innerHTML = '';
            
            if(stopsList.length === 0) {
                viewport.innerHTML = '<div class="empty-prompt">No matching bus stations found.</div>';
                return;
            }

            stopsList.forEach(stop => {
                const card = document.createElement('div');
                card.className = 'item-card';
                
                // Construct metrics readout element based on GPS availability
                let distanceMarkup = '';
                if (stop.distance !== undefined && stop.distance !== null) {
                    distanceMarkup = `<span style="color: var(--accent); font-weight: 500;">📏 ${stop.distance.toFixed(2)} km away</span>`;
                } else {
                    distanceMarkup = `<span>Station ID: ${stop.id}</span>`;
                }

                card.innerHTML = `
                    <div class="item-title">🚏 ${stop.name}</div>
                    <div class="item-sub">${distanceMarkup} <span style="color: var(--primary);">Live Stream →</span></div>
                `;
                
                card.onclick = () => {
                    currentSelectedStop = stop;
                    trackedVehicleId = null;
                    if (stop.lat && stop.lng) {
                        if(stopMarkerLayer) mapInstance.removeLayer(stopMarkerLayer);
                        if(busMarkerLayer) { mapInstance.removeLayer(busMarkerLayer); busMarkerLayer = null; }
                        
                        stopMarkerLayer = L.circleMarker([stop.lat, stop.lng], {
                            radius: 9, color: '#4ea8de', fillColor: '#fff', fillOpacity: 1, weight: 3
                        }).addTo(mapInstance).bindPopup(`<b>🚏 Stop: ${stop.name}</b>`).openPopup();
                        
                        // Dynamic bounds adjustment strategy to fit both positions comfortably on view
                        if (userCoordinates) {
                            let points = [
                                [userCoordinates.lat, userCoordinates.lng],
                                [stop.lat, stop.lng]
                            ];
                            mapInstance.fitBounds(points, { padding: [50, 50] });
                        } else {
                            mapInstance.setView([stop.lat, stop.lng], 15);
                        }
                    }
                    switchTab('arrivals');
                    startTrackingPulse();
                };
                viewport.appendChild(card);
            });
        }

        function startTrackingPulse() {
            stopTrackingPulse();
            document.getElementById('radar-pulse').style.display = 'inline-flex';
            renderArrivalsStream();
            trackingInterval = setInterval(renderArrivalsStream, 12000);
        }

        function stopTrackingPulse() {
            if(trackingInterval) { clearInterval(trackingInterval); trackingInterval = null; }
            document.getElementById('radar-pulse').style.display = 'none';
        }

        async function renderArrivalsStream() {
            if (!currentSelectedStop) return;
            document.getElementById('map-scope-title').innerText = currentSelectedStop.name;
            
            try {
                const [arrivalsRes, vehiclesRes] = await Promise.all([
                    fetch(`/api/stop_live/${currentSelectedStop.id}`),
                    fetch('/api/vehicles')
                ]);
                
                const rawArrivals = await arrivalsRes.json();
                const globalVehicles = await vehiclesRes.json();

                if (rawArrivals && rawArrivals.error) throw new Error(rawArrivals.error);

                let incomingList = safeExtractArray(rawArrivals);
                let vehicleArray = safeExtractArray(globalVehicles);

                if (activeTab !== 'arrivals') return;

                const viewport = document.getElementById('list-viewport');
                viewport.innerHTML = `<h3 style="margin: 0 0 12px 0; font-size:1rem; color: #fff;">Approaching Buses:</h3>`;

                if (incomingList.length === 0) {
                    viewport.innerHTML += `
                        <div class="empty-prompt" style="background: #1a1515; border-radius: 6px; padding: 15px; border: 1px solid #3a2222; text-align: left;">
                            <b style="color: var(--danger)">No live arrivals detected.</b><br><br>
                            The server reports zero active transit vehicles incoming over the next 30 minutes.
                        </div>
                    `;
                    document.getElementById('map-stats-badge').innerText = '0 Vehicles Tracked';
                    if(busMarkerLayer) { mapInstance.removeLayer(busMarkerLayer); busMarkerLayer = null; }
                    return;
                }

                document.getElementById('map-stats-badge').innerText = `${incomingList.length} Active Feeds`;

                incomingList.forEach(arrivalItem => {
                    try {
                        let lineDescr = autoExtract(arrivalItem, ['line', 'route', 'descr']);
                        let eta = autoExtract(arrivalItem, ['time', 'min', 'arr']);
                        let arrivalVehId = autoExtract(arrivalItem, ['veh', 'bus', 'code', 'id']);

                        let matchedGpsVehicle = vehicleArray.find(v => {
                            let globalVehId = autoExtract(v, ['veh', 'id', 'code', 'device']);
                            return matchVehicleIds(arrivalVehId, globalVehId);
                        });

                        let lat = matchedGpsVehicle ? parseFloat(autoExtract(matchedGpsVehicle, ['lat', 'y', 'latitude'])) : null;
                        let lng = matchedGpsVehicle ? parseFloat(autoExtract(matchedGpsVehicle, ['lng', 'lon', 'x', 'longitude'])) : null;

                        const card = document.createElement('div');
                        card.className = `item-card ${matchVehicleIds(trackedVehicleId, arrivalVehId) ? 'selected-bus' : ''}`;
                        
                        let gpsValid = (lat && lng && !isNaN(lat) && !isNaN(lng));
                        let gpsBadge = gpsValid 
                            ? `<span class="badge-live"><span class="badge-pulse"></span> Trackable</span>`
                            : `<span class="badge-live" style="background:#222; color:#777;">Off-Grid (No GPS)</span>`;

                        card.innerHTML = `
                            <div class="item-title">🚌 ${lineDescr}</div>
                            <div style="margin-top: 8px; display:flex; justify-content:space-between; align-items:center;">
                                <span class="badge-time">⏱️ ${typeof eta === 'number' ? eta + ' min' : eta}</span>
                                ${gpsBadge}
                            </div>
                        `;
                        
                        if (gpsValid) {
                            card.onclick = () => {
                                trackedVehicleId = arrivalVehId;
                                renderArrivalsStream(); 
                                updateBusGpsMarker(lat, lng, lineDescr, eta, arrivalVehId, true);
                            };

                            if (matchVehicleIds(trackedVehicleId, arrivalVehId)) {
                                updateBusGpsMarker(lat, lng, lineDescr, eta, arrivalVehId, false);
                            }
                        }
                        viewport.appendChild(card);
                    } catch (innerErr) {
                        console.error("Card processing exception:", innerErr);
                    }
                });

            } catch (e) {
                console.error(e);
                document.getElementById('list-viewport').innerHTML = `<div class="empty-prompt" style="color:var(--danger)">Insulation Error: ${e.message}</div>`;
            }
        }

        function updateBusGpsMarker(lat, lng, lineDescr, eta, vehicleId, panTo = true) {
            if (busMarkerLayer) {
                busMarkerLayer.setLatLng([lat, lng]);
                busMarkerLayer.setPopupContent(`<b>🚌 Active Bus: ${lineDescr}</b><br>ETA: ${eta}`);
            } else {
                busMarkerLayer = L.circleMarker([lat, lng], {
                    radius: 8, color: '#00b37e', fillColor: '#121214', fillOpacity: 0.9, weight: 3
                }).addTo(mapInstance);
                busMarkerLayer.bindPopup(`<b>🚌 Active Bus: ${lineDescr}</b><br>ETA: ${eta}`);
            }
            if (panTo) {
                busMarkerLayer.openPopup();
                mapInstance.setView([lat, lng], 15);
            }
        }

        document.getElementById('search-input').addEventListener('input', () => {
            sortAndRenderStops();
        });

        window.onload = () => {
            initMap();
            loadStopsIndex();
        };
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/stops')
def get_stops():
    return jsonify(fetch_transit_api("https://rest.citybus.gr/api/v1/el/112/stops"))

@app.route('/api/stop_live/<stop_id>')
def get_stop_live(stop_id):
    return jsonify(fetch_transit_api(f"https://rest.citybus.gr/api/v1/el/112/stops/live/{stop_id}"))

@app.route('/api/vehicles')
def get_global_vehicles():
    return jsonify(fetch_transit_api("https://rest.citybus.gr/api/v1/el/112/vehicles"))

# if __name__ == '__main__':
#     app.run(debug=True, port=5000)
app = app