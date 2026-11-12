"""FastAPI website and Bengaluru route-planning API with live traffic analysis."""
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
from route_finder.graph import RoadGraph, haversine_km
from route_finder.osm import demo_bengaluru_graph, load_bengaluru_graph
from route_finder.osrm_client import OSRMRouteError, fetch_dual_traffic_routes, fetch_osrm_route
from route_finder.storage import RouteHistory
from route_finder.traffic import BENGALURU_TRAFFIC_HOTSPOTS


load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("routewise.api")
PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_ROOT / "static"

_network: RoadGraph | None = None
_network_mode = "loading"
_network_lock = threading.Lock()


def _warm_network() -> None:
    """Load the road graph in the background; OSRM routes remain independent."""
    global _network, _network_mode
    if os.getenv("ENABLE_GRAPH_WARMUP", "true").casefold() not in {"1", "true", "yes"}:
        with _network_lock:
            _network_mode = "disabled"
        logger.info("Graph warmup is disabled; live OSRM routes remain available.")
        return
    try:
        network = load_bengaluru_graph(retries=1, request_timeout=40)
    except Exception:
        logger.exception("Live road graph is not ready; route lookups will use OSRM.")
        network = demo_bengaluru_graph()
        mode = "demo"
    else:
        mode = "live"
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
    optimize_for: Literal["distance", "time"] = "time"
    traffic_mode: Literal["normal", "peak", "offpeak"] = "normal"


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
    return {
        "status": "ok",
        "network": _network_mode,
        "service": "routewise-bengaluru",
        "traffic_monitoring": "active",
        "hotspots_monitored": len(BENGALURU_TRAFFIC_HOTSPOTS),
    }


@app.get("/api/traffic/hotspots")
def get_traffic_hotspots():
    """List monitored Bengaluru traffic choke points and severe congestion corridors."""
    return [
        {
            "id": h.id,
            "name": h.name,
            "lat": h.lat,
            "lon": h.lon,
            "radius_km": h.radius_km,
            "severity": h.severity,
            "description": h.description,
        }
        for h in BENGALURU_TRAFFIC_HOTSPOTS
    ]


@app.get("/api/locations/search")
def locations_search(q: str = Query(min_length=2, max_length=120)):
    try:
        return {"results": search_bengaluru(q)}
    except GeocodingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/locations/reverse")
def locations_reverse(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    try:
        return reverse_bengaluru(lat, lon)
    except GeocodingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/route")
def coordinate_route(request: CoordinateRouteRequest):
    if haversine_km(
        (request.start.lat, request.start.lon),
        (request.destination.lat, request.destination.lon),
    ) < 0.01:
        raise HTTPException(status_code=422, detail="Choose two different points for your route.")
    try:
        start = require_bengaluru_point(request.start.lat, request.start.lon)
        destination = require_bengaluru_point(request.destination.lat, request.destination.lon)
    except LocationOutsideBengaluru as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GeocodingError as exc:
        raise HTTPException(status_code=503, detail=f"Location validation is temporarily unavailable: {exc}") from exc

    try:
        dual_routes = fetch_dual_traffic_routes(
            (request.start.lat, request.start.lon),
            (request.destination.lat, request.destination.lon),
            traffic_mode=request.traffic_mode,
            base_url=os.getenv("OSRM_BASE_URL"),
        )
    except OSRMRouteError as exc:
        raise HTTPException(status_code=503, detail=f"Live road routing is temporarily unavailable: {exc}") from exc

    comparison = _compare_algorithms(
        (request.start.lat, request.start.lon),
        (request.destination.lat, request.destination.lon),
        request.optimize_for,
    )
    return {
        "start": {"label": start["label"], "lat": request.start.lat, "lon": request.start.lon},
        "destination": {
            "label": destination["label"],
            "lat": request.destination.lat,
            "lon": request.destination.lon,
        },
        "route": dual_routes["route"],
        "fastest_route": dual_routes["fastest_route"],
        "traffic_route": dual_routes["traffic_route"],
        "has_traffic_reroute": dual_routes["has_traffic_reroute"],
        "time_saved_min": dual_routes["time_saved_min"],
        "reroute_reason": dual_routes["reroute_reason"],
        "traffic_mode": dual_routes["traffic_mode"],
        "traffic_hotspots": dual_routes["traffic_hotspots"],
        "algorithm_comparison": comparison,
    }


@app.post("/routes")
def node_routes(request: NodeRouteRequest):
    with _network_lock:
        network, mode = _network, _network_mode
    if network is None or mode != "live":
        raise HTTPException(status_code=503, detail="The live Bengaluru road graph is still loading or unavailable.")
    results = []
    for method in ("dijkstra", "astar", "bfs", "dfs"):
        route = (
            getattr(network, method)(request.source, request.target, request.metric)
            if method in ("dijkstra", "astar")
            else getattr(network, method)(request.source, request.target)
        )
        if route:
            results.append(_route_summary(route))
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
                "Live routing is available. Graph comparisons are disabled on the free hosted service "
                "to keep it within memory limits; run locally with graph warmup enabled to compare "
                "Dijkstra, A*, BFS, and DFS."
            ),
        }
    if network is None:
        return {
            "available": False,
            "mode": "loading",
            "results": [],
            "message": "Live route is ready. The algorithm comparison is still loading.",
        }
    if mode != "live" or not network.coordinates:
        return {
            "available": False,
            "mode": "demo",
            "results": [],
            "message": "Live road routing is available; algorithm comparisons need the live road graph.",
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
            results.append(_route_summary(route))
    return {
        "available": bool(results),
        "mode": "live",
        "snapped_start_m": round(source_distance * 1000),
        "snapped_destination_m": round(target_distance * 1000),
        "results": results,
        "message": "Algorithm results use the cached OpenStreetMap road graph.",
    }


def _nearest_node(network: RoadGraph, point: tuple[float, float]) -> tuple[str, float]:
    node = min(network.coordinates, key=lambda candidate: haversine_km(point, network.coordinates[candidate]))
    return node, haversine_km(point, network.coordinates[node])


def _route_summary(route) -> dict:
    return {
        "algorithm": route.algorithm,
        "distance_km": route.distance_km,
        "duration_min": route.duration_min,
        "elapsed_ms": route.elapsed_ms,
        "nodes_explored": getattr(route, "nodes_explored", 0),
        "segments": max(0, len(route.nodes) - 1),
    }
