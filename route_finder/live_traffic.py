"""Traffic-aware route planning through TomTom's live Routing API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from .osrm_client import OSRMRouteError, async_fetch_osrm_raw_routes

logger = logging.getLogger("routewise.live_traffic")
TOMTOM_ROUTING_URL = "https://api.tomtom.com/routing/1/calculateRoute"


class LiveTrafficError(RuntimeError):
    """Raised when TomTom cannot provide a traffic-aware route response."""


def _normalise_tomtom_route(raw: dict[str, Any], index: int) -> dict[str, Any]:
    legs = raw.get("legs")
    summary = raw.get("summary")
    if not isinstance(legs, list) or not isinstance(summary, dict):
        raise LiveTrafficError("The traffic provider returned an incomplete route.")

    coordinates: list[tuple[float, float]] = []
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        for point in leg.get("points", []):
            try:
                coordinates.append((float(point["latitude"]), float(point["longitude"])))
            except (KeyError, TypeError, ValueError):
                continue
    if len(coordinates) < 2:
        raise LiveTrafficError("The traffic provider returned no usable route geometry.")

    try:
        duration_min = float(summary["travelTimeInSeconds"]) / 60
        distance_km = float(summary["lengthInMeters"]) / 1000
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveTrafficError("The traffic provider returned an invalid route summary.") from exc
    delay_min = max(0.0, float(summary.get("trafficDelayInSeconds") or 0) / 60)
    free_flow_seconds = summary.get("noTrafficTravelTimeInSeconds")
    free_flow_min = (
        max(0.0, float(free_flow_seconds) / 60)
        if free_flow_seconds is not None
        else max(0.0, duration_min - delay_min)
    )

    traffic_segments = []
    for section in raw.get("sections", []):
        if not isinstance(section, dict) or str(section.get("sectionType", "")).upper() != "TRAFFIC":
            continue
        try:
            start_index = int(section["startPointIndex"])
            end_index = int(section["endPointIndex"])
            segment_coordinates = coordinates[start_index : end_index + 1]
            if len(segment_coordinates) < 2:
                continue
            magnitude = int(section.get("magnitudeOfDelay", 0) or 0)
        except (KeyError, TypeError, ValueError):
            continue
        severity = {1: "minor", 2: "moderate", 3: "heavy", 4: "severe"}.get(magnitude, "unknown")
        traffic_segments.append({
            "coordinates": segment_coordinates,
            "severity": severity,
            "category": str(section.get("simpleCategory") or "TRAFFIC"),
            "delay_min": max(0.0, float(section.get("delayInSeconds") or 0) / 60),
            "speed_kmh": section.get("effectiveSpeedInKmh"),
            "name": section.get("streetName") or "Traffic affected road",
        })

    instructions = []
    guidance = raw.get("guidance")
    if isinstance(guidance, dict):
        raw_instructions = guidance.get("instructions", [])
        offsets = [
            float(item.get("routeOffsetInMeters", 0) or 0)
            for item in raw_instructions if isinstance(item, dict)
        ]
        valid_instructions = [item for item in raw_instructions if isinstance(item, dict)]
        for instruction_index, item in enumerate(valid_instructions):
            message = item.get("message") or item.get("combinedMessage")
            if not message:
                continue
            next_offset = offsets[instruction_index + 1] if instruction_index + 1 < len(offsets) else distance_km * 1000
            current_offset = float(item.get("routeOffsetInMeters", 0) or 0)
            instructions.append({
                "instruction": str(message),
                "distance_km": max(0.0, next_offset - current_offset) / 1000,
                "duration_min": max(0.0, float(item.get("travelTimeInSeconds", 0) or 0) / 60),
            })

    return {
        "coordinates": coordinates,
        "distance_km": distance_km,
        "duration_min": duration_min,
        "free_flow_min": free_flow_min,
        "traffic_delay_min": delay_min,
        "traffic_length_km": max(0.0, float(summary.get("trafficLengthInMeters") or 0) / 1000),
        "congestion_level": (
            "severe" if any(item["severity"] == "severe" for item in traffic_segments)
            else "heavy" if any(item["severity"] == "heavy" for item in traffic_segments)
            else "moderate" if any(item["severity"] == "moderate" for item in traffic_segments)
            else "clear"
        ),
        "traffic_segments": traffic_segments,
        "hotspots_detected": [],
        "instructions": instructions,
        "route_type": "fastest" if index == 0 else "traffic",
        "label": "Live traffic route" if index == 0 else "Live traffic alternative",
        "provider": "TomTom",
    }


async def async_fetch_tomtom_routes(
    points: list[tuple[float, float]],
    api_key: str,
    max_alternatives: int = 1,
) -> dict[str, Any]:
    """Fetch current-traffic ETAs, traffic-affected road sections, and alternatives."""
    if len(points) < 2:
        raise LiveTrafficError("At least two locations are required for routing.")
    if len(points) > 10:
        raise LiveTrafficError("Live routing supports up to ten stops.")
    route_locations = ":".join(f"{lat:.6f},{lon:.6f}" for lat, lon in points)
    params = {
        "key": api_key,
        "traffic": "true",
        "routeType": "fastest",
        "maxAlternatives": max(0, min(5, int(max_alternatives))),
        "routeRepresentation": "polyline",
        "computeTravelTimeFor": "all",
        "sectionType": "traffic",
        "instructionsType": "text",
        "language": "en-GB",
    }
    try:
        async with httpx.AsyncClient(timeout=14, follow_redirects=True) as client:
            response = await client.get(
                f"{TOMTOM_ROUTING_URL}/{route_locations}/json",
                params=params,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        raise LiveTrafficError("TomTom live traffic is temporarily unavailable.") from exc

    raw_routes = payload.get("routes") if isinstance(payload, dict) else None
    if not isinstance(raw_routes, list) or not raw_routes:
        raise LiveTrafficError("TomTom did not return a drivable route for these locations.")
    routes = []
    for index, raw in enumerate(raw_routes):
        if not isinstance(raw, dict):
            continue
        try:
            routes.append(_normalise_tomtom_route(raw, index))
        except LiveTrafficError:
            logger.warning("Skipping an incomplete live traffic alternative from TomTom.")
    if not routes:
        raise LiveTrafficError("TomTom did not return usable route geometry.")
    routes.sort(key=lambda route: route["duration_min"])
    routes[0]["route_type"] = "fastest"
    routes[0]["label"] = "Fastest with live traffic"
    if len(routes) > 1:
        routes[1]["route_type"] = "traffic"
        routes[1]["label"] = "Live traffic alternative"
    return {
        "routes": routes,
        "traffic": {
            "available": True,
            "configured": True,
            "provider": "TomTom",
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "message": "Route times and highlighted slow sections use current traffic data.",
        },
    }


async def async_fetch_route_options(
    points: list[tuple[float, float]],
    api_key: str | None = None,
    osrm_base_url: str | None = None,
) -> dict[str, Any]:
    """Prefer live TomTom data; fall back to plainly-labelled OSRM baseline routes."""
    if api_key:
        try:
            return await async_fetch_tomtom_routes(points, api_key)
        except LiveTrafficError as exc:
            logger.info("Live traffic lookup failed; keeping the OSRM fallback: %s", exc)
            traffic_message = str(exc)
    else:
        traffic_message = "Add TOMTOM_API_KEY to the service environment to enable live traffic."

    try:
        candidates = await async_fetch_osrm_raw_routes(points, base_url=osrm_base_url, alternatives=True)
    except OSRMRouteError:
        raise
    routes = []
    for index, candidate in enumerate(candidates):
        routes.append({
            **candidate,
            "free_flow_min": candidate["duration_min"],
            "traffic_delay_min": None,
            "traffic_length_km": 0.0,
            "congestion_level": "unknown",
            "traffic_segments": [],
            "hotspots_detected": [],
            "route_type": "fastest" if index == 0 else "traffic",
            "label": "Road route estimate" if index == 0 else "Alternative road route",
            "provider": "OSRM",
        })
    if routes:
        routes[0]["route_type"] = "fastest"
        if len(routes) > 1:
            routes[1]["route_type"] = "traffic"
    return {
        "routes": routes,
        "traffic": {
            "available": False,
            "configured": bool(api_key),
            "provider": "TomTom",
            "updated_at": None,
            "message": traffic_message,
        },
    }
