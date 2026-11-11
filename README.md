# Optimised Route Finder

A Bengaluru road routing project that compares Dijkstra, A*, breadth-first search (BFS), and depth-first search (DFS). It includes a Streamlit interface, FastAPI service, OpenStreetMap road-network loading with GraphML caching, and SQLite route history.

## Features

- OpenStreetMap drive network for Bengaluru via OSMnx; downloaded once and cached at `data/bengaluru.graphml`. Transient Overpass failures are retried with backoff.
- Dijkstra and A* can optimise distance or estimated travel time. A* uses straight-line distance as an admissible lower bound; for time, it divides by the fastest speed in the network.
- BFS and DFS show unweighted traversal routes for algorithm comparison; they do not guarantee the shortest distance or time.
- Route metrics include distance, estimated duration, search runtime, and segment count. Search history is stored in `data/routes.db`.
- Modern Streamlit UI with landmark-based route selection, interactive map, performance chart, and saved search history.
- A clearly labeled schematic Bengaluru demo network keeps the interface usable when the public Overpass service is unavailable. Choose **Retry live road data** in the sidebar to retry.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

The first application run downloads the Bengaluru driving network from OpenStreetMap and may take a few minutes. Internet access is needed for that initial download; subsequent runs use the cache. The public Overpass servers can be busy; when that happens, the app retries and then switches to a small illustrative landmark network until you retry the live data.

Optional settings can be copied from `.env.example` to `.env`. `ROUTE_PLACE`, `GRAPH_PATH`, and `DATABASE_PATH` control the map area, GraphML cache location, and SQLite history file.

## Run

```bash
streamlit run app.py
uvicorn api:app --reload
```

API: `GET /health`, `POST /routes` with `{"source":"node id","target":"node id","metric":"distance"}` or `"time"`, and `GET /history?limit=50`. API route endpoints accept OSM node IDs; the Streamlit UI lets users choose named landmarks and snaps them to nearby road nodes. The network loader uses OSMnx's simplified drive graph and a 30 km/h fallback speed if the OSM network lacks speed tags.

## Tests

```bash
python -m pytest -q
```

Tests use a tiny in-memory graph and do not download map data.
