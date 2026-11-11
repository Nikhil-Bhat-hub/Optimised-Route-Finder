"""Small client for OSRM's public, no-key demo routing service."""
from __future__ import annotations

import json
import math
import os
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_OSRM_URL = "https://router.project-osrm.org"
_REQUEST_INTERVAL_SECONDS = 1.05
_request_lock = threading.Lock()
_last_request_started = 0.0


class OSRMRouteError(RuntimeError):
    """Raised when the external routing service cannot return a usable route."""


def fetch_osrm_route(
    start: tuple[float, float],
    end: tuple[float, float],
    base_url: str | None = None,
) -> dict[str, Any]:
    """Get a driving route between (latitude, longitude) pairs.

    Returned geometry is converted from OSRM's [longitude, latitude] order to
    the [latitude, longitude] order expected by Folium.
    """
    start_lat, start_lon = _validate_coordinate(start)
    end_lat, end_lon = _validate_coordinate(end)
    service_url = (base_url or os.getenv("OSRM_BASE_URL") or DEFAULT_OSRM_URL).rstrip("/")
    if not service_url.startswith(("https://", "http://")):
        raise OSRMRouteError("OSRM_BASE_URL must be an http:// or https:// URL.")

    coordinates = (
        f"{start_lon:.6f},{start_lat:.6f};{end_lon:.6f},{end_lat:.6f}"
    )
    query = urlencode({
        "overview": "full",
        "geometries": "geojson",
        "alternatives": "false",
        "steps": "false",
        "generate_hints": "false",
    })
    request = Request(
        f"{service_url}/route/v1/driving/{coordinates}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "RoutewiseBengaluru/1.0 (OpenStreetMap routing demo)",
        },
    )

    global _last_request_started
    try:
        # The public demo policy asks clients not to exceed one request per
        # second. The lock also spaces concurrent requests in this app process.
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

    try:
        route = payload["routes"][0]
        raw_coordinates = route["geometry"]["coordinates"]
        distance_m = float(route["distance"])
        duration_s = float(route["duration"])
        path = [(float(lat), float(lon)) for lon, lat in raw_coordinates]
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
        "provider": "OSRM · OpenStreetMap",
    }


def _validate_coordinate(point: tuple[float, float]) -> tuple[float, float]:
    try:
        lat, lon = float(point[0]), float(point[1])
    except (IndexError, TypeError, ValueError) as exc:
        raise OSRMRouteError("Each location must contain latitude and longitude.") from exc
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise OSRMRouteError("A location has invalid latitude or longitude values.")
    return lat, lon
