"""Client for OSRM's routing service with multi-route support and traffic-aware rerouting."""
from __future__ import annotations

import json
import math
import os
import asyncio
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .traffic import (
    FLOOD_RISK_POINTS,
    RouteTrafficAnalysis,
    analyze_flood_risk,
    analyze_route_traffic,
    compute_avoidance_waypoint,
)

DEFAULT_OSRM_URL = "https://router.project-osrm.org"
_REQUEST_INTERVAL_SECONDS = 1.05
_request_lock = threading.Lock()
_last_request_started = 0.0
_async_request_lock = asyncio.Lock()
_async_last_request_started = 0.0


class OSRMRouteError(RuntimeError):
    """Raised when the external routing service cannot return a usable route."""


def _execute_osrm_request(service_url: str, coords_str: str, alternatives: bool) -> dict[str, Any]:
    query = urlencode({
        "overview": "full",
        "geometries": "geojson",
        "alternatives": "true" if alternatives else "false",
        "steps": "true",
        "generate_hints": "false",
    })
    request = Request(
        f"{service_url}/route/v1/driving/{coords_str}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "RoutewiseBengaluru/1.0 (OpenStreetMap routing demo)",
        },
    )

    global _last_request_started
    try:
        with _request_lock:
            wait = _REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_started)
            if wait > 0:
                time.sleep(wait)
            _last_request_started = time.monotonic()
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise OSRMRouteError(f"The routing service returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise OSRMRouteError("The routing service could not be reached right now.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OSRMRouteError("The routing service returned an unreadable response.") from exc

    if not isinstance(payload, dict):
        raise OSRMRouteError("The routing service returned an invalid response.")
    if payload.get("code") != "Ok":
        if payload.get("code") == "NoRoute":
            raise OSRMRouteError("No drivable route was found between these locations.")
        raise OSRMRouteError("The routing service could not find a route for these locations.")

    return payload


def _parse_single_route(route: dict[str, Any]) -> dict[str, Any]:
    try:
        raw_coordinates = route["geometry"]["coordinates"]
        distance_m = float(route["distance"])
        duration_s = float(route["duration"])
        path = [(float(lat), float(lon)) for lon, lat in raw_coordinates]
        instructions = _route_instructions(route.get("legs", []))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise OSRMRouteError("The routing service returned incomplete route data.") from exc

    if (
        len(path) < 2
        or not math.isfinite(distance_m)
        or not math.isfinite(duration_s)
        or distance_m < 0
        or duration_s < 0
        or any(
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
            for lat, lon in path
        )
    ):
        raise OSRMRouteError("The routing service returned invalid route data.")

    return {
        "distance_km": distance_m / 1000,
        "duration_min": duration_s / 60,
        "coordinates": path,
        "instructions": instructions,
        "provider": "OSRM · OpenStreetMap",
    }


def fetch_osrm_raw_routes(
    points: list[tuple[float, float]],
    base_url: str | None = None,
    alternatives: bool = False,
) -> list[dict[str, Any]]:
    """Fetch one or more candidate routes for a sequence of (lat, lon) points."""
    if len(points) < 2:
        raise OSRMRouteError("At least two points are required for routing.")
    validated = [_validate_coordinate(p) for p in points]
    service_url = (base_url or os.getenv("OSRM_BASE_URL") or DEFAULT_OSRM_URL).rstrip("/")
    if not service_url.startswith(("https://", "http://")):
        raise OSRMRouteError("OSRM_BASE_URL must be an http:// or https:// URL.")

    coords_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in validated)
    payload = _execute_osrm_request(service_url, coords_str, alternatives=alternatives)
    routes_raw = payload.get("routes", [])
    if not routes_raw:
        raise OSRMRouteError("No routes returned by routing service.")

    parsed_routes = []
    for r in routes_raw:
        try:
            parsed_routes.append(_parse_single_route(r))
        except OSRMRouteError:
            continue

    if not parsed_routes:
        raise OSRMRouteError("No valid route could be parsed.")
    return parsed_routes


def fetch_osrm_route(
    start: tuple[float, float],
    end: tuple[float, float],
    base_url: str | None = None,
) -> dict[str, Any]:
    """Get the primary driving route between (latitude, longitude) pairs.
    Maintains full backward compatibility.
    """
    routes = fetch_osrm_raw_routes([start, end], base_url, alternatives=False)
    return routes[0]


def fetch_dual_traffic_routes(
    start: tuple[float, float],
    end: tuple[float, float],
    traffic_mode: str = "normal",
    base_url: str | None = None,
) -> dict[str, Any]:
    """Find the best driving routes, analyze traffic congestion, and automatically
    calculate a bypass route if the primary corridor experiences significant traffic.

    Returns:
      fastest_route: The optimal route avoiding heavy traffic (or fastest clear path).
      traffic_route: The route with traffic bottlenecks & delays highlighted.
      traffic_summary: Details on detected traffic, delays, time saved, and rerouting reason.
    """
    # 1. Fetch routes from OSRM with alternatives
    candidate_routes = fetch_osrm_raw_routes([start, end], base_url=base_url, alternatives=True)
    primary = candidate_routes[0]

    # 2. Analyze traffic on the primary route
    primary_analysis = analyze_route_traffic(
        primary["coordinates"],
        primary["duration_min"],
        mode=traffic_mode,  # type: ignore
    )

    primary_with_traffic = {
        **primary,
        "free_flow_min": primary_analysis.free_flow_min,
        "duration_min": primary_analysis.duration_with_traffic_min,
        "traffic_delay_min": primary_analysis.traffic_delay_min,
        "congestion_level": primary_analysis.congestion_level,
        "hotspots_detected": primary_analysis.hotspots_detected,
        "route_type": "traffic",
        "label": "Route with Traffic",
    }

    # 3. Check alternative routes if primary has traffic delays
    best_alternate: dict[str, Any] | None = None
    best_alternate_analysis: RouteTrafficAnalysis | None = None

    if primary_analysis.traffic_delay_min >= 2.0 or primary_analysis.congestion_level != "clear":
        # Check alternatives provided by OSRM first
        for alt in candidate_routes[1:]:
            alt_analysis = analyze_route_traffic(
                alt["coordinates"],
                alt["duration_min"],
                mode=traffic_mode,  # type: ignore
            )
            # If this alternative route is faster with traffic than the primary route
            if alt_analysis.duration_with_traffic_min < primary_analysis.duration_with_traffic_min - 0.5:
                if (
                    best_alternate_analysis is None
                    or alt_analysis.duration_with_traffic_min < best_alternate_analysis.duration_with_traffic_min
                ):
                    best_alternate = alt
                    best_alternate_analysis = alt_analysis

        # If OSRM's alternatives didn't bypass the bottleneck, compute a detour waypoint!
        if (
            best_alternate is None
            and primary_analysis.hotspots_detected
        ):
            worst_spot = primary_analysis.hotspots_detected[0]
            detour_point = compute_avoidance_waypoint(start, end, worst_spot)
            try:
                detour_routes = fetch_osrm_raw_routes(
                    [start, detour_point, end],
                    base_url=base_url,
                    alternatives=False,
                )
                if detour_routes:
                    detour_route = detour_routes[0]
                    detour_analysis = analyze_route_traffic(
                        detour_route["coordinates"],
                        detour_route["duration_min"],
                        mode=traffic_mode,  # type: ignore
                    )
                    # Use detour if it is faster than sitting in primary traffic
                    if detour_analysis.duration_with_traffic_min < primary_analysis.duration_with_traffic_min - 0.5:
                        best_alternate = detour_route
                        best_alternate_analysis = detour_analysis
            except Exception:
                pass  # Fall back to primary if detour route fails

    # 4. Formulate the dual response
    if best_alternate is not None and best_alternate_analysis is not None:
        time_saved = max(0.1, round(primary_with_traffic["duration_min"] - best_alternate_analysis.duration_with_traffic_min, 1))
        spot_names = ", ".join(s["name"] for s in primary_analysis.hotspots_detected[:2])
        reroute_reason = (
            f"Heavy traffic detected on {spot_names} (+{primary_analysis.traffic_delay_min:.0f} min delay). "
            f"Automatically rerouted via bypass route to save {time_saved:.0f} min."
        )

        fastest_route = {
            **best_alternate,
            "free_flow_min": best_alternate_analysis.free_flow_min,
            "duration_min": best_alternate_analysis.duration_with_traffic_min,
            "traffic_delay_min": best_alternate_analysis.traffic_delay_min,
            "congestion_level": best_alternate_analysis.congestion_level,
            "hotspots_detected": best_alternate_analysis.hotspots_detected,
            "route_type": "fastest",
            "label": "Fastest Route (Traffic Avoided)",
            "time_saved_min": time_saved,
        }
        traffic_route = primary_with_traffic
        has_traffic_reroute = True
    else:
        # If no significant traffic or no faster detour was found:
        # Fastest route is primary (clear)
        fastest_route = {
            **primary,
            "free_flow_min": primary_analysis.free_flow_min,
            "duration_min": primary_analysis.duration_with_traffic_min,
            "traffic_delay_min": primary_analysis.traffic_delay_min,
            "congestion_level": primary_analysis.congestion_level,
            "hotspots_detected": primary_analysis.hotspots_detected,
            "route_type": "fastest",
            "label": "Fastest Route",
            "time_saved_min": 0.0,
        }
        # If an alternative candidate exists from OSRM, show it as comparison
        if len(candidate_routes) > 1:
            alt = candidate_routes[1]
            alt_analysis = analyze_route_traffic(alt["coordinates"], alt["duration_min"], mode=traffic_mode)  # type: ignore
            traffic_route = {
                **alt,
                "free_flow_min": alt_analysis.free_flow_min,
                "duration_min": alt_analysis.duration_with_traffic_min,
                "traffic_delay_min": alt_analysis.traffic_delay_min,
                "congestion_level": alt_analysis.congestion_level,
                "hotspots_detected": alt_analysis.hotspots_detected,
                "route_type": "traffic",
                "label": "Alternative Route",
            }
        else:
            # Simulate high-traffic comparison so user can always see traffic vs clear
            sim_peak_analysis = analyze_route_traffic(
                primary["coordinates"],
                primary["duration_min"],
                mode="peak",
            )
            traffic_route = {
                **primary,
                "free_flow_min": sim_peak_analysis.free_flow_min,
                "duration_min": sim_peak_analysis.duration_with_traffic_min,
                "traffic_delay_min": sim_peak_analysis.traffic_delay_min,
                "congestion_level": "heavy" if sim_peak_analysis.traffic_delay_min > 0 else "clear",
                "hotspots_detected": sim_peak_analysis.hotspots_detected,
                "route_type": "traffic",
                "label": "Peak Hour Traffic Route",
            }

        has_traffic_reroute = False
        time_saved = 0.0
        reroute_reason = "Traffic is flowing smoothly. Primary route is optimal."

    # Collect all detected unique hotspots for map warning pins
    all_hotspots = []
    seen_ids = set()
    for route_obj in (traffic_route, fastest_route):
        for spot in route_obj.get("hotspots_detected", []):
            if spot["id"] not in seen_ids:
                seen_ids.add(spot["id"])
                all_hotspots.append(spot)

    return {
        "fastest_route": fastest_route,
        "traffic_route": traffic_route,
        "has_traffic_reroute": has_traffic_reroute,
        "time_saved_min": time_saved,
        "reroute_reason": reroute_reason,
        "traffic_mode": traffic_mode,
        "traffic_hotspots": all_hotspots,
        # Default route key for backward compatibility
        "route": fastest_route,
    }


def _validate_coordinate(point: tuple[float, float]) -> tuple[float, float]:
    try:
        lat, lon = float(point[0]), float(point[1])
    except (IndexError, TypeError, ValueError) as exc:
        raise OSRMRouteError("Each location must contain latitude and longitude.") from exc
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise OSRMRouteError("A location has invalid latitude or longitude values.")
    return lat, lon


def _route_instructions(legs: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    directions = []
    for leg in legs:
        for step in leg.get("steps", []):
            maneuver = step.get("maneuver", {})
            action = str(maneuver.get("type", "continue")).replace("_", " ")
            modifier = str(maneuver.get("modifier", "")).replace("_", " ")
            road = str(step.get("name") or "the road")
            if action == "depart":
                instruction = f"Head toward {road}"
            elif action == "arrive":
                instruction = "Arrive at your destination"
            elif action == "turn" and modifier:
                instruction = f"Turn {modifier} onto {road}"
            elif action == "roundabout":
                exit_number = maneuver.get("exit")
                instruction = f"Take exit {exit_number} at the roundabout onto {road}" if exit_number else f"Take the roundabout onto {road}"
            elif action in ("merge", "fork", "on ramp", "off ramp") and modifier:
                instruction = f"{action.capitalize()} {modifier} onto {road}"
            else:
                instruction = f"Continue on {road}"
            directions.append({
                "instruction": instruction,
                "distance_km": float(step.get("distance", 0)) / 1000,
                "duration_min": float(step.get("duration", 0)) / 60,
            })
    return directions


async def async_fetch_osrm_raw_routes(
    points: list[tuple[float, float]],
    base_url: str | None = None,
    alternatives: bool = False,
) -> list[dict[str, Any]]:
    """HTTPX async equivalent of fetch_osrm_raw_routes for FastAPI handlers."""
    if len(points) < 2:
        raise OSRMRouteError("At least two points are required for routing.")
    validated = [_validate_coordinate(point) for point in points]
    service_url = (base_url or os.getenv("OSRM_BASE_URL") or DEFAULT_OSRM_URL).rstrip("/")
    if not service_url.startswith(("https://", "http://")):
        raise OSRMRouteError("OSRM_BASE_URL must be an http:// or https:// URL.")
    try:
        import httpx
    except ImportError as exc:
        raise OSRMRouteError("Install httpx to use the hosted async routing API.") from exc

    global _async_last_request_started
    async with _async_request_lock:
        wait = _REQUEST_INTERVAL_SECONDS - (time.monotonic() - _async_last_request_started)
        if wait > 0:
            await asyncio.sleep(wait)
        _async_last_request_started = time.monotonic()

    coords_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in validated)
    url = f"{service_url}/route/v1/driving/{coords_str}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "alternatives": "true" if alternatives else "false",
        "steps": "true",
        "generate_hints": "false",
    }
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(
                url,
                params=params,
                headers={"Accept": "application/json", "User-Agent": "RoutewiseBengaluru/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise OSRMRouteError(f"The routing service returned HTTP {exc.response.status_code}.") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise OSRMRouteError("The routing service could not be reached right now.") from exc
    if not isinstance(payload, dict):
        raise OSRMRouteError("The routing service returned an invalid response.")
    if payload.get("code") != "Ok":
        if payload.get("code") == "NoRoute":
            raise OSRMRouteError("No drivable route was found between these locations.")
        raise OSRMRouteError("The routing service could not find a route for these locations.")
    parsed = []
    for raw_route in payload.get("routes", []):
        try:
            parsed.append(_parse_single_route(raw_route))
        except OSRMRouteError:
            continue
    if not parsed:
        raise OSRMRouteError("No valid route could be parsed.")
    return parsed


async def async_fetch_osrm_duration_matrix(
    points: list[tuple[float, float]],
    base_url: str | None = None,
) -> list[list[float]]:
    """Fetch a driving-time matrix for TSP stop ordering with the OSRM Table API."""
    if not 2 <= len(points) <= 10:
        raise OSRMRouteError("Route optimization supports 2 to 10 points.")
    validated = [_validate_coordinate(point) for point in points]
    service_url = (base_url or os.getenv("OSRM_BASE_URL") or DEFAULT_OSRM_URL).rstrip("/")
    if not service_url.startswith(("https://", "http://")):
        raise OSRMRouteError("OSRM_BASE_URL must be an http:// or https:// URL.")
    try:
        import httpx
    except ImportError as exc:
        raise OSRMRouteError("Install httpx to use the hosted async routing API.") from exc
    coords_str = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in validated)
    global _async_last_request_started
    async with _async_request_lock:
        wait = _REQUEST_INTERVAL_SECONDS - (time.monotonic() - _async_last_request_started)
        if wait > 0:
            await asyncio.sleep(wait)
        _async_last_request_started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(
                f"{service_url}/table/v1/driving/{coords_str}",
                params={"annotations": "duration"},
                headers={"Accept": "application/json", "User-Agent": "RoutewiseBengaluru/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        raise OSRMRouteError("The routing service could not create a stop-time matrix.") from exc
    matrix = payload.get("durations") if isinstance(payload, dict) else None
    if not isinstance(matrix, list) or len(matrix) != len(points):
        raise OSRMRouteError("The routing service returned an incomplete stop-time matrix.")
    try:
        converted = [[float(value) / 60 for value in row] for row in matrix]
    except (TypeError, ValueError) as exc:
        raise OSRMRouteError("The routing service returned invalid stop durations.") from exc
    if any(not math.isfinite(value) or value < 0 for row in converted for value in row):
        raise OSRMRouteError("The routing service returned unreachable stops.")
    return converted


async def async_fetch_dual_traffic_routes(
    points: list[tuple[float, float]],
    traffic_mode: str = "normal",
    base_url: str | None = None,
    avoid_flood: bool = False,
) -> dict[str, Any]:
    """Plan a multi-stop route asynchronously and label modelled conditions honestly."""
    if len(points) < 2:
        raise OSRMRouteError("At least two points are required for routing.")
    points = [_validate_coordinate(point) for point in points]
    candidates = await async_fetch_osrm_raw_routes(points, base_url=base_url, alternatives=True)

    def decorate(route: dict[str, Any], mode: str) -> tuple[dict[str, Any], RouteTrafficAnalysis]:
        analysis = analyze_route_traffic(route["coordinates"], route["duration_min"], mode=mode)  # type: ignore[arg-type]
        return ({
            **route,
            "free_flow_min": analysis.free_flow_min,
            "duration_min": analysis.duration_with_traffic_min,
            "traffic_delay_min": analysis.traffic_delay_min,
            "congestion_level": analysis.congestion_level,
            "hotspots_detected": analysis.hotspots_detected,
            "route_type": "route",
        }, analysis)

    primary, primary_analysis = decorate(candidates[0], traffic_mode)
    options: list[tuple[dict[str, Any], RouteTrafficAnalysis, list[dict[str, Any]]]] = []
    for raw in candidates:
        route, analysis = decorate(raw, traffic_mode)
        rain_risks = analyze_flood_risk(route["coordinates"])
        options.append((route, analysis, rain_risks))

    # If the selected route crosses a static monsoon caution point, try a public
    # routing-engine alternative that preserves all waypoint stops.
    if avoid_flood and options[0][2]:
        risky_point = options[0][2][0]
        detour = compute_avoidance_waypoint(points[0], points[-1], risky_point)
        try:
            detour_candidates = await async_fetch_osrm_raw_routes(
                [points[0], detour, *points[1:]], base_url=base_url, alternatives=False
            )
            route, analysis = decorate(detour_candidates[0], traffic_mode)
            risks = analyze_flood_risk(route["coordinates"])
            if not risks or len(risks) < len(options[0][2]):
                options.append((route, analysis, risks))
        except OSRMRouteError:
            pass

    selected = min(
        options,
        key=lambda entry: (len(entry[2]) if avoid_flood else 0, entry[1].duration_with_traffic_min),
    )
    fastest_route = {
        **selected[0],
        "route_type": "fastest",
        "label": "Recommended route",
        "rain_risks": selected[2],
    }

    primary_rain = options[0][2]
    traffic_route, traffic_analysis = primary, primary_analysis
    if traffic_mode != "peak" and primary_analysis.traffic_delay_min < 2:
        traffic_route, traffic_analysis = decorate(candidates[0], "peak")
        traffic_route["label"] = "Peak-hour model"
    else:
        traffic_route["label"] = "Selected traffic model"
    traffic_route = {**traffic_route, "route_type": "traffic", "rain_risks": primary_rain}

    hotspots = []
    seen = set()
    for route in (traffic_route, fastest_route):
        for hotspot in route.get("hotspots_detected", []):
            if hotspot["id"] not in seen:
                seen.add(hotspot["id"])
                hotspots.append(hotspot)
    has_reroute = selected[0] is not options[0][0]
    time_saved = max(0, round(traffic_route["duration_min"] - fastest_route["duration_min"], 1))
    return {
        "route": fastest_route,
        "fastest_route": fastest_route,
        "traffic_route": traffic_route,
        "has_traffic_reroute": has_reroute,
        "time_saved_min": time_saved,
        "reroute_reason": (
            "An available route avoided a modeled hotspot or static rain-risk area."
            if has_reroute
            else "Times use an OpenStreetMap road route and a modeled congestion estimate."
        ),
        "traffic_mode": traffic_mode,
        "traffic_hotspots": hotspots,
        "rain_mode": avoid_flood,
        "rain_risks": primary_rain,
        "estimate_notice": "Traffic and rain-risk conditions are planning estimates, not live sensor feeds.",
    }
