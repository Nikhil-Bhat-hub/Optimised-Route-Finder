# Routewise Bengaluru

Routewise is a Bengaluru-only route planner built around a small FastAPI service and a responsive, map-first website. Choose any point in the city by searching for a place or clicking the map, then see a road route, distance, estimated drive time, and turn-by-turn instructions.

The project also demonstrates classic route-search algorithms: Dijkstra, A*, BFS, and DFS. The optional graph comparison uses a locally cached OpenStreetMap road graph. It is enabled during local development and disabled on Render's free instance to keep the public route service within its memory budget. The hosted application still provides live OSRM routing and Bengaluru place lookup.

## Features

- English-language responsive interface with interactive OpenStreetMap map.
- Search Bengaluru streets, landmarks, and neighbourhoods, or select a point directly on the map.
- Location validation rejects places outside Bengaluru with a clear city-boundary message.
- Live driving route, distance, estimated drive time, and step-by-step directions via the free OSRM demo service.
- Optional Dijkstra, A*, BFS, and DFS comparison against a cached OpenStreetMap drive graph.
- FastAPI JSON endpoints and interactive API documentation at `/docs`.
- Streamlit algorithm explorer retained for local use.

## Run locally

Python 3.11 or newer is recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn api:app --reload
```

Open <http://127.0.0.1:8000>. API documentation is at <http://127.0.0.1:8000/docs> and health status is at <http://127.0.0.1:8000/health>.

The first local launch downloads and caches the Bengaluru driving graph through OSMnx and Overpass. That download can take several minutes or fail when public Overpass servers are busy. Live route requests use OSRM independently of graph loading. To skip graph loading on a small machine, set `ENABLE_GRAPH_WARMUP=false`.

The original Streamlit algorithm explorer remains available:

```bash
streamlit run app.py
```

## API endpoints

- `GET /api/locations/search?q=Koramangala` — user-submitted search, limited to Bengaluru.
- `GET /api/locations/reverse?lat=12.9352&lon=77.6245` — validates and labels a selected map point.
- `POST /api/route` — finds a live road route and returns route metrics and directions.
- `POST /routes` — compares the graph algorithms using graph node IDs when a live graph is loaded.
- `GET /history?limit=50` — retrieves locally saved graph-route history.
- `GET /health` — service and graph status.

Example coordinate route request:

```json
{
  "start": {"lat": 12.9767, "lon": 77.5713, "label": "Majestic"},
  "destination": {"lat": 12.9352, "lon": 77.6245, "label": "Koramangala"},
  "optimize_for": "time"
}
```

`optimize_for` controls the graph algorithm comparison metric. The hosted OSRM route follows the public driving profile.

## Free data services and usage

- **Nominatim** provides Bengaluru search and reverse geocoding. Requests are submitted by the user, cached in-process for 24 hours, and throttled to at most one request per second. The service sends an identifying User-Agent. The public service has a usage policy and should not be used as a high-volume or autocomplete backend; switch `NOMINATIM_BASE_URL` to a provider you control before scaling up.
- **OSRM demo** provides driving routes without an API key. It is a community demo service with reasonable-use limits and no uptime guarantee. For sustained public traffic, operate your own compatible routing server or use a provider with an appropriate plan.
- **OpenStreetMap tiles** are displayed with attribution. Follow the tile usage policy and use a dedicated provider for sustained public traffic.

Public services can be busy or temporarily unavailable. The app gives a readable retry message instead of returning a broken map or route.

## Deploy to Render

The repository includes a single-service Render Blueprint. The FastAPI process serves both the website and API, so the free deployment needs only one web service. It installs the lean `requirements-web.txt` set; the full `requirements.txt` also includes Streamlit and OSMnx for local graph exploration.

1. Connect the repository to Render and apply the Blueprint in `render.yaml`.
2. Open the service URL. The site is at `/`, API docs at `/docs`, and the health endpoint at `/health`.

The free web service sleeps after inactivity and can take about a minute to wake. Its filesystem is temporary, so in-process geocoding caches and any local graph or SQLite files are lost on restarts. Graph warmup is disabled on this profile; route planning remains live through OSRM. See Render's current [free service limits](https://render.com/docs/free).

## Configuration

Copy `.env.example` to `.env` for local overrides. The main settings are:

- `OSRM_BASE_URL` — OSRM-compatible routing server.
- `NOMINATIM_BASE_URL` — Nominatim-compatible search server.
- `NOMINATIM_USER_AGENT` — identifying User-Agent for geocoding requests.
- `ENABLE_GRAPH_WARMUP` — load the local OSM road graph (`true` by default).
- `ROUTE_PLACE`, `GRAPH_PATH`, and `DATABASE_PATH` — graph area and local cache/history paths.

## Tests

```bash
python -m pytest -q
```

Tests use a small in-memory graph and mocked service responses; they do not download OSM data.

## Resume project summary

**Routewise Bengaluru** — Built a full-stack route-planning service with FastAPI, an interactive Leaflet map, OpenStreetMap geocoding, OSRM road directions, city-boundary validation, and classic graph-search comparisons. Deployed as a single free web service on Render.

Adapt the summary to your contribution and include measured results only after you have verified them. No project can guarantee a particular hiring outcome.
