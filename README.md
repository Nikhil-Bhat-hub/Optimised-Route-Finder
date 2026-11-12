# Routewise Bengaluru

An open-source Bengaluru route-planning project built with FastAPI, Leaflet, OpenStreetMap, OSRM, and classic graph-search algorithms.

**Live app:** [routewise-bengaluru.onrender.com](https://routewise-bengaluru.onrender.com) · **API docs:** [/docs](https://routewise-bengaluru.onrender.com/docs)

Routewise is designed for exploring route-planning trade-offs inside Bengaluru. Pick points on the map, search for places, use your current location, add stops, and compare route estimates. A compact OpenStreetMap graph can power local Dijkstra, A*, BFS, and DFS comparisons alongside road routes from OSRM.

## Features

- Map clicks and place search for locations inside Bengaluru. Points outside the supported city area receive a clear boundary message.
- Browser geolocation for a starting point, shareable route links, and an **Open in Google Maps** export.
- Multi-stop routes and a nearest-neighbor plus 2-opt stop-order optimizer.
- Traffic-aware route times and highlighted traffic-affected road sections through TomTom Routing API when a key is configured.
- Automatic live route alternatives where TomTom returns them, plus a truthful OSRM estimate fallback when live traffic is unavailable.
- Journey summaries with estimated average speed, provider-reported live delay, and stop count.
- A map playback of sampled frontier expansions and a count of explored graph nodes.
- An optional monsoon-caution overlay with static underpass markers; these are not live flood reports and do not change the route.
- An illustrative Namma Metro comparison.
- Responsive mobile route-planner sheet that can be dragged between map and planning views.
- FastAPI endpoints and interactive OpenAPI documentation at /docs.

## Data and estimate limits

Route geometry and baseline drive durations come from the public OSRM routing service over OpenStreetMap road data. Public routes may be rate-limited or temporarily unavailable.

With `TOMTOM_API_KEY` configured, each route request automatically uses TomTom's traffic-aware Routing API for current ETAs, alternative routes, and traffic-affected sections along the route. TomTom's free tier currently includes 20,000 Routing API requests per month. Without a valid key or when the provider is unavailable, the app keeps route planning available through OSRM and labels its time as an estimate without live traffic adjustment. Traffic is refreshed whenever a route is requested; the app does not continuously poll while a route is open. The service key is read only by FastAPI and is never sent to the browser.

Monsoon areas are static planning cautions, not current flood reports. Metro times use approximate station locations, average speeds, and an assumed wait; they are not an operational timetable. Check [official BMRCL timings](https://english.bmrc.co.in/metro-timings/) before travel.

The public Nominatim, OSRM, TomTom, and OpenStreetMap tile services are shared community services. They can slow down, rate-limit, or change availability. For sustained production traffic, configure hosted providers with suitable service terms and capacity.

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

### Enable live traffic

Create a free [TomTom developer account](https://my.tomtom.com/) and generate an API key. Add it as `TOMTOM_API_KEY` in your local `.env` file, or in the Render service's environment settings. The key remains server-side. The page applies current traffic automatically when a route is requested and displays traffic sections on the selected route. Without the key, routes continue to work with baseline OSRM times and the page labels live traffic as unavailable.

### Build the compact algorithm graph

The graph builder queries OpenStreetMap through OSMnx/Overpass and keeps a major-road network for the Render free instance. The output is gzip-compressed and must remain under 30 MiB.

~~~bash
python -m pip install -r requirements-graph-build.txt
python scripts/build_compact_graph.py
~~~

GitHub Actions can run the builder from **Actions → Build Bengaluru compact road graph → Run workflow**. The builder tries the global VK Maps Overpass instance first, then Private.coffee, then the default Overpass instance, and accepts a comma-separated `OVERPASS_URLS` override for other endpoints. It uses the VK endpoint's published no-limit policy to skip slot probing for that single-instance query. The workflow checks the size, commits the graph when it changes, and the Render service auto-deploys from main. Public Overpass capacity can still affect a build. If the graph is missing, place search and OSRM routes remain available, while graph comparison and playback report that the graph is unavailable.

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
| GET | /api/traffic/status | Whether TomTom live traffic is configured |
| GET | /api/locations/search?q=Koramangala | Search for a Bengaluru place |
| GET | /api/locations/reverse?lat=12.93&lon=77.62 | Check and label a map point |
| GET | /api/rain/hazards | Static monsoon-caution locations |
| POST | /api/route | Live traffic routes when configured, otherwise OSRM estimates, plus algorithm results |
| POST | /api/route/optimize-order | Optimize up to ten stops with OSRM durations and 2-opt |
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
  "optimize_for": "time"
}
~~~

The API validates every selected stop against the supported Bengaluru area. `GET /api/traffic/status` reports whether the live provider key is configured without exposing it.

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
