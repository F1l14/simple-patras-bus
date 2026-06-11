# Patras Bus · Live

A fast, self-hostable live map for the Patras city bus network ("https://patra.citybus.gr"), rebuilt as a single-file Flask app with a dark full-screen map UI.

## Features
- **Live arrivals** for any stop, auto-refreshing every 10 s, with each approaching bus shown on the map as a colored, smoothly-moving pin labeled with its line number
- **Nearby stops** sorted by distance from you, with walking-time estimates
- **Lines browser** — every line with its official color, route geometry drawn on the map, direction switcher, and the full stop sequence
- **Timetables** per stop with a day picker, per-line filtering, and the next departure highlighted
- **Favorites** (saved stops, stored locally) and shareable deep links (`#stop=263`, `#line=101`)
- **Search** across stops and lines, stop dots on the map when zoomed in, geolocation with accuracy circle

## Running locally
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/flask --app api/index.py run --port 5000
```
Then open http://127.0.0.1:5000.

## Hosting
The repo is ready to deploy on https://vercel.com for personal use (`vercel.json` routes everything to `api/index.py`).

## How it works
The backend harvests the short-lived bearer token that patra.citybus.gr embeds in its HTML, proxies the rest.citybus.gr REST API (stops, lines, live vehicle positions, route geometry, stop sequences, timetables), caches the static data in memory, and serves a single-page Leaflet frontend. The upstream API's 404-for-no-data responses are normalized to empty lists.
