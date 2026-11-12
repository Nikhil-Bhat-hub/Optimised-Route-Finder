"""FastAPI website and Bengaluru route-planning API with optional live traffic."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from route_finder.geocoding import (
    GeocodingError,
    LocationOutsideBengaluru,
    require_bengaluru_point,
    reverse_bengaluru,
    search_bengaluru,
)
from route_finder.compact_graph import load_compact_graph
from route_finder.graph import RoadGraph, haversine_km
from route_finder.metro import estimate_metro
from route_finder.osrm_client import (
    OSRMRouteError,
    async_fetch_osrm_duration_matrix,
)
from route_finder.live_traffic import async_fetch_route_options
from route_finder.storage import RouteHistory
from route_finder.traffic import FLOOD_RISK_POINTS
from route_finder.tsp import optimize_stop_order


load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("routewise.api")
PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_ROOT / "static"

_network: RoadGraph | None = None
_network_mode = "loading"
_network_lock = threading.Lock()


def _warm_network() -> None:
    """Load the checked-in compact graph; hosted road routing remains OSRM-backed."""
    global _network, _network_mode
    if os.getenv("ENABLE_GRAPH_WARMUP", "true").casefold() not in {"1", "true", "yes"}:
        with _network_lock:
            _network_mode = "disabled"
        logger.info("Graph comparisons are disabled; OSRM route planning remains available.")
        return
    try:
        graph_path = Path(os.getenv("COMPACT_GRAPH_PATH", str(PROJECT_ROOT / "data/bengaluru-compact.json.gz")))
        network = load_compact_graph(graph_path)
    except Exception:
        logger.warning("Compact graph is not available; algorithm comparisons are temporarily disabled.")
        with _network_lock:
            _network = None
            _network_mode = "disabled"
        return
    else:
        mode = "compact"
    with _network_lock:
        _network = network
        _network_mode = mode
    logger.info("Road graph ready in %s mode.", mode)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    warm_task = asyncio.create_task(asyncio.to_thread(_warm_network))
    yield
    if not warm_task.done():
        warm_task.cancel()


app = FastAPI(
    title="Routewise Bengaluru API",
    version="2.1.0",
    description="Bengaluru-only place lookup, traffic-aware route planning, and algorithm comparison.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class RoutePoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str = Field(default="Selected point", max_length=160)


class CoordinateRouteRequest(BaseModel):
    start: RoutePoint
    destination: RoutePoint
    waypoints: list[RoutePoint] = Field(default_factory=list, max_length=8)
    optimize_for: Literal["distance", "time"] = "time"


class OptimizeOrderRequest(BaseModel):
    points: list[RoutePoint] = Field(min_length=3, max_length=10)


class TransitEstimateRequest(BaseModel):
    start: RoutePoint
    destination: RoutePoint


class NodeRouteRequest(BaseModel):
    """Backward-compatible graph-node endpoint used by the original API."""
    source: str
    target: str
    metric: Literal["distance", "time"] = "distance"


@app.get("/", include_in_schema=False)
def website():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    traffic_configured = bool(os.getenv("TOMTOM_API_KEY"))
    return {
        "status": "ok",
        "network": _network_mode,
        "service": "routewise-bengaluru",
        "traffic_provider": "TomTom",
        "live_traffic_configured": traffic_configured,
        "routing_provider": "OSRM",
    }


@app.get("/api/traffic/status")
def traffic_status():
    """Expose live-feed availability without revealing the provider key."""
    configured = bool(os.getenv("TOMTOM_API_KEY"))
    return {
        "available": configured,
        "provider": "TomTom",
        "message": (
            "Live traffic is requested automatically when a route is planned."
            if configured
            else "Add TOMTOM_API_KEY to the service environment to enable live traffic."
        ),
    }


@app.get("/api/rain/hazards")
def get_rain_hazards():
    """Return static monsoon caution areas (not live flood observations)."""
    return {"source": "static planning cautions", "hazards": FLOOD_RISK_POINTS}


@app.get("/api/locations/search")
async def locations_search(q: str = Query(min_length=2, max_length=120)):
    try:
        return {"results": await asyncio.to_thread(search_bengaluru, q)}
    except GeocodingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/locations/reverse")
async def locations_reverse(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    try:
        return await asyncio.to_thread(reverse_bengaluru, lat, lon)
    except GeocodingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/route/optimize-order")
async def route_optimize_order(request: OptimizeOrderRequest):
    points = request.points
    if any(haversine_km((a.lat, a.lon), (b.lat, b.lon)) < 0.01 for a, b in zip(points, points[1:])):
        raise HTTPException(status_code=422, detail="Each stop must be a different location.")
    try:
        await asyncio.gather(*(
            asyncio.to_thread(require_bengaluru_point, point.lat, point.lon)
            for point in points
        ))
        matrix = await async_fetch_osrm_duration_matrix(
            [(point.lat, point.lon) for point in points],
            base_url=os.getenv("OSRM_BASE_URL"),
        )
        matrix = [
            [value if source != target else 0.0 for target, value in enumerate(row)]
            for source, row in enumerate(matrix)
        ]
        order, total = optimize_stop_order(matrix)
    except LocationOutsideBengaluru as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GeocodingError as exc:
        raise HTTPException(status_code=503, detail=f"Location validation is temporarily unavailable: {exc}") from exc
    except (OSRMRouteError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"Could not optimize this stop order: {exc}") from exc
    return {
        "points": [points[index].model_dump() for index in order],
        "order": order,
        "estimated_drive_min": total,
        "method": "nearest-neighbor initialization + 2-opt improvement",
        "estimate_notice": "Stop ordering uses current OSRM road durations; it does not use live traffic adjustments.",
    }


@app.post("/api/transit/estimate")
async def transit_estimate(request: TransitEstimateRequest):
    try:
        await asyncio.gather(
            asyncio.to_thread(require_bengaluru_point, request.start.lat, request.start.lon),
            asyncio.to_thread(require_bengaluru_point, request.destination.lat, request.destination.lon),
        )
    except LocationOutsideBengaluru as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GeocodingError as exc:
        raise HTTPException(status_code=503, detail=f"Location validation is temporarily unavailable: {exc}") from exc
    result = estimate_metro(
        (request.start.lat, request.start.lon),
        (request.destination.lat, request.destination.lon),
    )
    result["estimate_notice"] = (
        "This is an illustrative transit estimate, not a live timetable. Check BMRCL for current service times."
    )
    return result


@app.post("/api/route")
async def coordinate_route(request: CoordinateRouteRequest):
    locations = [request.start, *request.waypoints, request.destination]
    if any(
        haversine_km((a.lat, a.lon), (b.lat, b.lon)) < 0.01
        for a, b in zip(locations, locations[1:])
    ):
        raise HTTPException(status_code=422, detail="Choose two different points for your route.")
    try:
        validated = await asyncio.gather(*(
            asyncio.to_thread(require_bengaluru_point, point.lat, point.lon)
            for point in locations
        ))
    except LocationOutsideBengaluru as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GeocodingError as exc:
        raise HTTPException(status_code=503, detail=f"Location validation is temporarily unavailable: {exc}") from exc

    try:
        points = [(point.lat, point.lon) for point in locations]
        route_data = await async_fetch_route_options(
            points,
            api_key=os.getenv("TOMTOM_API_KEY"),
            osrm_base_url=os.getenv("OSRM_BASE_URL"),
        )
    except OSRMRouteError as exc:
        raise HTTPException(status_code=503, detail=f"Live road routing is temporarily unavailable: {exc}") from exc

    comparison = await asyncio.to_thread(
        _compare_algorithms, points[0], points[-1], request.optimize_for
    )
    routes = route_data["routes"]
    if not routes:
        raise HTTPException(status_code=503, detail="No usable road route was returned.")
    for route in routes:
        route["rain_risks"] = []
    selected_route = routes[0]
    alternate_route = routes[1] if len(routes) > 1 else None
    live_traffic = route_data["traffic"]
    return {
        "start": {"label": validated[0]["label"], "lat": request.start.lat, "lon": request.start.lon},
        "waypoints": [
            {"label": point["label"], "lat": request_point.lat, "lon": request_point.lon}
            for point, request_point in zip(validated[1:-1], request.waypoints)
        ],
        "destination": {
            "label": validated[-1]["label"],
            "lat": request.destination.lat,
            "lon": request.destination.lon,
        },
        "route": selected_route,
        "routes": routes,
        "fastest_route": selected_route,
        "traffic_route": alternate_route or selected_route,
        "has_traffic_reroute": bool(alternate_route),
        "time_saved_min": (
            max(0, round(alternate_route["duration_min"] - selected_route["duration_min"], 1))
            if alternate_route else 0
        ),
        "reroute_reason": live_traffic["message"],
        "traffic_hotspots": [],
        "rain_risks": selected_route["rain_risks"],
        "live_traffic": live_traffic,
        "estimate_notice": (
            "Route timing and marked traffic sections use TomTom's current traffic-aware routing data."
            if live_traffic["available"]
            else "Live traffic is unavailable. The displayed time is an OSRM route estimate without live traffic adjustment."
        ),
        "algorithm_comparison": comparison,
    }


@app.post("/routes")
def node_routes(request: NodeRouteRequest):
    with _network_lock:
        network, mode = _network, _network_mode
    if network is None or mode not in {"live", "compact"}:
        raise HTTPException(status_code=503, detail="The compact Bengaluru road graph is still loading or unavailable.")
    results = []
    for method in ("dijkstra", "astar", "bfs", "dfs"):
        route = (
            getattr(network, method)(request.source, request.target, request.metric)
            if method in ("dijkstra", "astar")
            else getattr(network, method)(request.source, request.target)
        )
        if route:
            results.append(_route_summary(route, network))
            try:
                RouteHistory().save(request.source, request.target, request.metric, route)
            except OSError:
                logger.exception("Could not save route history.")
    return {"source": request.source, "target": request.target, "metric": request.metric, "routes": results}


@app.get("/history")
def history(limit: int = Query(50, ge=1, le=500)):
    return RouteHistory().recent(limit)


def _compare_algorithms(
    start: tuple[float, float],
    destination: tuple[float, float],
    metric: str,
) -> dict:
    with _network_lock:
        network, mode = _network, _network_mode
    if mode == "disabled":
        return {
            "available": False,
            "mode": "disabled",
            "results": [],
            "message": (
                "OSRM route planning is available. The compact Bengaluru graph is not loaded yet, "
                "so local algorithm comparisons are temporarily unavailable."
            ),
        }
    if network is None:
        return {
            "available": False,
            "mode": "loading",
            "results": [],
            "message": "Live route is ready. The algorithm comparison is still loading.",
        }
    if mode not in {"live", "compact"} or not network.coordinates:
        return {
            "available": False,
            "mode": mode,
            "results": [],
            "message": "Algorithm comparisons need the compact Bengaluru road graph; live route lookup remains available.",
        }

    source_node, source_distance = _nearest_node(network, start)
    target_node, target_distance = _nearest_node(network, destination)
    if source_distance > 1.5 or target_distance > 1.5:
        return {
            "available": False,
            "mode": "live",
            "results": [],
            "message": "The live route is available, but its points are too far from this graph's roads to compare algorithms.",
        }

    results = []
    for method in ("dijkstra", "astar", "bfs", "dfs"):
        route = (
            getattr(network, method)(source_node, target_node, metric)
            if method in ("dijkstra", "astar")
            else getattr(network, method)(source_node, target_node)
        )
        if route:
            results.append(_route_summary(route, network))
    mode_label = "compact OSM road graph" if mode == "compact" else "cached OpenStreetMap road graph"
    return {
        "available": bool(results),
        "mode": mode,
        "snapped_start_m": round(source_distance * 1000),
        "snapped_destination_m": round(target_distance * 1000),
        "results": results,
        "message": f"Algorithm results use the {mode_label}.",
    }


def _nearest_node(network: RoadGraph, point: tuple[float, float]) -> tuple[str, float]:
    return network.nearest_node(point)


def _route_summary(route, network: RoadGraph | None = None) -> dict:
    visited = getattr(route, "visited_order", [])
    edges = getattr(route, "explored_edges", [])
    return {
        "algorithm": route.algorithm,
        "distance_km": route.distance_km,
        "duration_min": route.duration_min,
        "elapsed_ms": route.elapsed_ms,
        "nodes_explored": getattr(route, "nodes_explored", 0),
        "segments": max(0, len(route.nodes) - 1),
        "visited_coordinates": [
            list(network.coordinates[node]) for node in visited
            if network is not None and node in network.coordinates
        ],
        "explored_edges": [
            [list(network.coordinates[a]), list(network.coordinates[b])]
            for a, b in edges
            if network is not None and a in network.coordinates and b in network.coordinates
        ],
    }
