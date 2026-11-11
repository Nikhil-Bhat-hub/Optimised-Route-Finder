# Optimised Route Finder

A Python-based route planning and algorithm-comparison application using OpenStreetMap road data. It demonstrates Dijkstra, A*, BFS, and DFS on a real drivable road network, with a Streamlit interface, Folium map visualization, SQLite search history, and an optional FastAPI endpoint.

> **Scope note:** travel times are estimates derived from road speed attributes. This project does not provide live traffic or guarantee real-world arrival times.

## Features

- Download/cache a drivable Bengaluru road graph from OpenStreetMap with OSMnx.
- Geocode user-entered locations and snap them to nearby road-network nodes.
- Find routes using Dijkstra and A* with distance or estimated travel-time weights.
- Run BFS and DFS as unweighted graph traversal baselines (not optimal for weighted roads).
- Compare execution time, number of explored nodes, route distance, and estimated duration.
- Display the routes on an interactive Folium map.
- Store recent route searches in SQLite.
- Optional FastAPI `/route` and `/health` endpoints.
- Unit tests for the four algorithms.

## Requirements

- Python 3.10 or newer
- Internet connection for first-time map download and Nominatim geocoding
- OpenStreetMap attribution when using/displaying OSM data

## Quick start (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts/download_graph.py
streamlit run app.py
```

Open the Streamlit URL shown in the terminal (usually `http://localhost:8501`). The first graph download may take a few minutes and creates `data/bengaluru.graphml`; this generated map file is intentionally excluded from Git because it is large and can be regenerated.

## Quick start (macOS/Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts/download_graph.py
streamlit run app.py
```

## Run the API

```bash
uvicorn backend.main:app --reload
```

- `GET /health` — service health check.
- `POST /route` — calculates an A* or Dijkstra route.

Example request:

```json
{
  "source": "Indian Institute of Science, Bengaluru",
  "destination": "Cubbon Park, Bengaluru",
  "optimize_for": "length",
  "algorithm": "astar"
}
```

Interactive API docs are available at `http://127.0.0.1:8000/docs`.

## Run tests

```bash
pytest -q
```

## Project structure

```text
Optimised-Route-Finder/
├── algorithms/        # Dijkstra, A*, BFS, DFS
├── backend/           # OSM graph loader and FastAPI service
├── database/          # SQLite route history
├── visualization/     # Map and chart helpers
├── scripts/           # Road graph download utility
├── tests/             # Algorithm unit tests
├── data/              # Generated graph and local SQLite DB (gitignored)
├── app.py             # Streamlit dashboard
├── requirements.txt
└── README.md
```

## Algorithm notes

| Algorithm | Weight-aware | Guarantees least-cost route? | Use in this project |
|---|---:|---:|---|
| Dijkstra | Yes | Yes, with non-negative weights | Primary baseline |
| A* | Yes | Yes, with an admissible heuristic | Primary optimized search |
| BFS | No | Minimum number of edges only | Unweighted baseline |
| DFS | No | No | Traversal baseline |

A* uses straight-line geographic distance as its lower-bound heuristic for length. For travel time, the implementation uses a conservative 1 m/s lower-bound estimate. Benchmark timings depend on the graph, machine, cache state, and selected locations; results shown by the app are measured at runtime, not pre-filled claims.

## Data, attribution, and responsible use

Road-network data comes from [OpenStreetMap](https://www.openstreetmap.org/), © OpenStreetMap contributors, under the [ODbL](https://www.openstreetmap.org/copyright). Keep attribution visible in maps and derivative data. Follow the Nominatim usage policy; do not send bulk or rapid geocoding requests. For production use, use a compliant hosted geocoding/routing provider and its applicable terms.

## Limitations and future enhancements

- No live traffic feed; estimated travel time is based on OSM road-speed metadata.
- The initial region is Bengaluru. Change `ROUTE_PLACE` and `GRAPH_PATH` to use another supported place.
- Road-closure support, user accounts, live GPS tracking, and alternative-route diversity are future enhancements.
- The public Nominatim service has usage limits; geocode sparingly and consider a dedicated provider for deployment.

## License

This project code is provided for academic and learning use. OpenStreetMap data remains subject to its own license and attribution requirements.
