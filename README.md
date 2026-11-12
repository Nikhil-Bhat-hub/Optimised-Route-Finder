# Routewise Bengaluru

An open-source Bengaluru route-planning project built with FastAPI, Leaflet, OpenStreetMap, OSRM, and classic graph-search algorithms.

**Live app:** [routewise-bengaluru.onrender.com](https://routewise-bengaluru.onrender.com) · **API docs:** [/docs](https://routewise-bengaluru.onrender.com/docs)

Routewise is designed for exploring route-planning trade-offs inside Bengaluru. Pick points on the map, search for places, use your current location, add stops, and compare route estimates. A compact OpenStreetMap graph can power local Dijkstra, A*, BFS, and DFS comparisons alongside road routes from OSRM.

## Features

- Map clicks and place search for locations inside Bengaluru. Points outside the supported city area receive a clear boundary message.
- Browser geolocation for a starting point, shareable route links, and an **Open in Google Maps** export.
- Multi-stop routes and a nearest-neighbor plus 2-opt stop-order optimizer.
- Journey efficiency summaries with estimated average speed, modeled delay share, and stop count.
- Typical, peak, and off-peak traffic scenarios with corridor delay estimates and available alternate OSRM routes.
- A map playback of sampled frontier expansions and a count of explored graph nodes.
- A monsoon-caution toggle that marks a few static underpass risk areas and attempts to find a route around them.
- An approximate terrain profile from Open-Elevation and an illustrative Namma Metro comparison.
- Responsive mobile route-planner sheet that can be dragged between map and planning views.
- FastAPI endpoints and interactive OpenAPI documentation at /docs.

## Data and estimate limits

Route geometry and baseline drive durations come from the public OSRM routing service over OpenStreetMap road data. Public routes may be rate-limited or temporarily unavailable.

Traffic values are **modeled estimates**, not live traffic observations. The peak/off-peak factors and known corridor hotspots help compare scenarios; they do not use a live traffic provider or guarantee an actual travel time.

Monsoon areas are static planning cautions, not current flood reports. Elevation is approximate terrain data and may differ from the road surface. Metro times use approximate station locations, average speeds, and an assumed wait; they are not an operational timetable. Check [official BMRCL timings](https://english.bmrc.co.in/metro-timings/) before travel.

The public Nominatim, OSRM, Open-Elevation, and OpenStreetMap tile services are shared community services. They can slow down, rate-limit, or change availability. For sustained production traffic, configure hosted providers with suitable service terms and capacity.

## Run the FastAPI app locally

Python 3.11 or newer is recommended.

~~~bash
git clone https://github.com/Nikhil-Bhat-hub/Optimised-Route-Finder.git
cd Optimised-Route-Finder
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-web.txt
uvicorn api:app --reload
~~~

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Road routing and place lookup work without an API key. Algorithm comparisons are enabled when the compact graph is present at data/bengaluru-compact.json.gz.

### Build the compact algorithm graph

The graph builder queries OpenStreetMap through OSMnx/Overpass and keeps a major-road network for the Render free instance. The output is gzip-compressed and must remain under 30 MiB.

~~~bash
python -m pip install -r requirements-graph-build.txt
python scripts/build_compact_graph.py
~~~

GitHub Actions can run the builder from **Actions → Build Bengaluru compact road graph → Run workflow**. The builder tries the Private.coffee Overpass instance first, then the default Overpass instance, and accepts a comma-separated `OVERPASS_URLS` override for other endpoints. The workflow checks the size, commits the graph when it changes, and the Render service auto-deploys from main. Public Overpass capacity can still affect a build. If the graph is missing, place search and OSRM routes remain available, while graph comparison and playback report that the graph is unavailable.

### Run the Streamlit explorer

The original algorithm dashboard remains available for local exploration:

~~~bash
python -m pip install -r requirements.txt
streamlit run app.py
~~~

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /health | Service, graph, and routing status |
| GET | /api/locations/search?q=Koramangala | Search for a Bengaluru place |
| GET | /api/locations/reverse?lat=12.93&lon=77.62 | Check and label a map point |
| GET | /api/traffic/hotspots | Modeled traffic corridors |
| GET | /api/rain/hazards | Static monsoon-caution locations |
| POST | /api/route | Multi-stop route, modeled conditions, and algorithm results |
| POST | /api/route/optimize-order | Optimize the order of up to ten points with OSRM durations and 2-opt |
| POST | /api/elevation | Look up terrain elevations along a sampled route |
| POST | /api/transit/estimate | Compare with an illustrative metro estimate |
| POST | /routes | Backward-compatible node-based graph algorithm results |
| GET | /history | Recent node-based route history |

Example route request:

~~~json
{
  "start": {"lat": 12.9767, "lon": 77.5713, "label": "Majestic"},
  "waypoints": [
    {"lat": 12.9756, "lon": 77.6066, "label": "MG Road"}
  ],
  "destination": {"lat": 12.9352, "lon": 77.6245, "label": "Koramangala"},
  "optimize_for": "time",
  "traffic_mode": "peak",
  "avoid_flood": false
}
~~~

The API validates every selected stop against the supported Bengaluru area. traffic_mode accepts normal, peak, or offpeak.

## Tests and checks

~~~bash
python -m pip install -r requirements-web.txt pytest
python -m pytest -q
node --check static/app.js
~~~

GitHub Actions runs the unit suite on pushes to main and pull requests.

## Deployment

The Render Blueprint in render.yaml defines a free web service using requirements-web.txt and uvicorn api:app. Configure the service to deploy from main; pushes to the repository then trigger deployment automatically. The free instance may spin down when idle, so the first request after inactivity can take longer.

## Attribution and license

Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), available under the [ODbL](https://www.openstreetmap.org/copyright). The project is licensed under the MIT License.

