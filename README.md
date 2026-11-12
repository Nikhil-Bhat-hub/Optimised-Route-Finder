# Routewise Bengaluru — Traffic-Aware Route Finder

**Live Website on Render:** [https://routewise-bengaluru.onrender.com](https://routewise-bengaluru.onrender.com)

Routewise is an intelligent, traffic-aware Bengaluru route planner and algorithm comparison platform built with FastAPI, Leaflet.js, OpenStreetMap, and OSRM. Choose any two points across Bengaluru by searching or clicking directly on the map. The system analyzes real-time corridor congestion, identifies choke points (such as Central Silk Board and Bellandur ORR), automatically computes bypass routes, and displays both the **Route with Traffic** and the **Fastest Route (Traffic Avoided)** simultaneously.

---

## Key Features

- **Dual-Route Traffic Intelligence**:
  - Automatically detects congestion bottlenecks on the primary route.
  - Automatically calculates and suggests an alternate bypass path to save travel time.
  - Displays both routes on the interactive map:
    - **⚡ Solid Emerald Green**: Fastest route avoiding traffic choke points.
    - **⚠️ Dashed Coral Red**: Standard corridor with traffic delay indicators.
  - Dual route selection cards allow users to switch active views and compare distance, duration, and time saved.
- **Bengaluru Choke Point Monitoring**:
  - Real-time detection across chronic congestion hubs (Silk Board, Ecospace ORR, Tin Factory, Hebbal Flyover, Marathahalli, Sony World Signal, Goraguntepalya, etc.).
  - Interactive map hazard markers with severity levels and estimated delays.
- **Traffic Condition Scenarios**:
  - Toggle between **Normal / Daytime**, **Peak Rush Hour (Simulated)**, and **Off-Peak / Night** conditions.
- **Graph Algorithm Comparison**:
  - Compares **Dijkstra**, **A\*** (with admissible Haversine heuristic), **BFS**, and **DFS** on drivable road networks with `nodes_explored` metrics.
- **City Boundary Validation**:
  - Restricts routing strictly inside Bengaluru's municipal and urban boundaries with friendly guidance.
- **FastAPI Endpoints & Swagger Docs**:
  - Fully documented REST API available at `/docs`.
- **Streamlit Algorithm Dashboard**:
  - Available for local benchmarking, analytics, and data-science exploration via `app.py`.

---

## Live Deployment

The application is deployed on Render as a unified web service:
- **Web Application:** [https://routewise-bengaluru.onrender.com](https://routewise-bengaluru.onrender.com)
- **Interactive API Documentation:** [https://routewise-bengaluru.onrender.com/docs](https://routewise-bengaluru.onrender.com/docs)
- **Service Health Check:** [https://routewise-bengaluru.onrender.com/health](https://routewise-bengaluru.onrender.com/health)

*(Note: Render free-tier instances spin down during periods of inactivity and may take ~45–60 seconds to wake on initial load).*

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Responsive Leaflet.js web application |
| `GET` | `/health` | Service status, traffic monitoring, and graph state |
| `GET` | `/api/traffic/hotspots` | List monitored Bengaluru traffic choke points |
| `GET` | `/api/locations/search?q=Koramangala` | Bengaluru-restricted place search via Nominatim |
| `GET` | `/api/locations/reverse?lat=12.93&lon=77.62` | City-boundary validation and reverse labeling |
| `POST`| `/api/route` | Traffic analysis, dual-route generation, and algorithm metrics |
| `POST`| `/routes` | Node-based graph algorithm comparison |
| `GET` | `/history` | Recent route queries stored in SQLite |

### Example Request (`POST /api/route`):

```json
{
  "start": {
    "lat": 12.9767,
    "lon": 77.5713,
    "label": "Majestic"
  },
  "destination": {
    "lat": 12.9352,
    "lon": 77.6245,
    "label": "Koramangala"
  },
  "optimize_for": "time",
  "traffic_mode": "peak"
}
```

### Example Response:

```json
{
  "has_traffic_reroute": true,
  "time_saved_min": 14.0,
  "reroute_reason": "Heavy traffic detected on Central Silk Board Junction (+18 min delay). Automatically rerouted via bypass route to save 14 min.",
  "fastest_route": {
    "distance_km": 15.2,
    "duration_min": 34.0,
    "congestion_level": "clear",
    "coordinates": [[12.9767, 77.5713], ...]
  },
  "traffic_route": {
    "distance_km": 14.1,
    "duration_min": 48.0,
    "traffic_delay_min": 18.0,
    "congestion_level": "severe",
    "hotspots_detected": [{"name": "Central Silk Board Junction", "severity": "severe"}]
  }
}
```

---

## Run Locally

Python 3.10 or newer is recommended:

```bash
git clone https://github.com/Nikhil-Bhat-hub/Optimised-Route-Finder.git
cd Optimised-Route-Finder

# Create and activate virtual environment
python -m venv .venv
# On Windows: .venv\Scripts\Activate.ps1
# On macOS/Linux: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server
uvicorn api:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

To launch the Streamlit explorer:
```bash
streamlit run app.py
```

---

## Run Tests

```bash
python -m pytest -q
```

All tests run in-memory with mocked service responses for deterministic CI/CD execution.

---

## License

This project is open-source under the MIT License. OpenStreetMap data is available under the Open Database License (ODbL).
