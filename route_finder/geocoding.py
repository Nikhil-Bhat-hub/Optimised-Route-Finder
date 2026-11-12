"""Rate-limited Bengaluru search and reverse geocoding via public Nominatim."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GeocodingError(RuntimeError):
    """Raised when Nominatim cannot resolve a location reliably."""


class LocationOutsideBengaluru(ValueError):
    """Raised when a selected point does not resolve to Bengaluru."""


# A broad viewport includes Bengaluru's urban outskirts. Nominatim's address
# fields are checked as well, so nearby towns inside the rectangle are rejected.
_BENGALURU_BOUNDS = (12.70, 77.30, 13.25, 77.95)  # south, west, north, east
_CACHE_TTL_SECONDS = 24 * 60 * 60
_MIN_REQUEST_INTERVAL = 1.05
_CACHE_MAX_ENTRIES = 512
_BASE_URL = "https://nominatim.openstreetmap.org"
_USER_AGENT = (
    "RoutewiseBengaluru/1.0 "
    "(https://github.com/Nikhil-Bhat-hub/Optimised-Route-Finder)"
)
_lock = threading.Lock()
_last_request = 0.0
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()


def is_inside_bengaluru_bounds(lat: float, lon: float) -> bool:
    south, west, north, east = _BENGALURU_BOUNDS
    return south <= lat <= north and west <= lon <= east


def is_bengaluru_address(address: dict[str, Any], display_name: str = "") -> bool:
    """Check city and district fields returned by Nominatim for Bengaluru."""
    for key in ("city", "municipality", "city_district", "state_district", "county", "town"):
        value = str(address.get(key, "")).casefold()
        if "bengaluru" in value or "bangalore" in value:
            return True
    name = display_name.casefold()
    return "bengaluru" in name or "bangalore" in name


def search_bengaluru(query: str, limit: int = 6) -> list[dict[str, Any]]:
    query = query.strip()
    if len(query) < 2:
        return []
    south, west, north, east = _BENGALURU_BOUNDS
    params = {
        "q": f"{query}, Bengaluru",
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": min(max(limit, 1), 8),
        "countrycodes": "in",
        "viewbox": f"{west},{north},{east},{south}",
        "bounded": 1,
        "accept-language": "en",
    }
    payload = _nominatim("/search", params)
    matches = []
    for item in payload if isinstance(payload, list) else []:
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        display_name = str(item.get("display_name", ""))
        if not is_inside_bengaluru_bounds(lat, lon):
            continue
        if not is_bengaluru_address(item.get("address", {}), display_name):
            continue
        matches.append({
            "label": str(item.get("name") or display_name.split(",")[0]),
            "display_name": display_name,
            "lat": lat,
            "lon": lon,
        })
    return matches


def reverse_bengaluru(lat: float, lon: float) -> dict[str, Any]:
    """Resolve a clicked map point and report whether it is in Bengaluru."""
    lat, lon = float(lat), float(lon)
    if not is_inside_bengaluru_bounds(lat, lon):
        return _outside_result(lat, lon)
    payload = _nominatim("/reverse", {
        "lat": f"{lat:.6f}",
        "lon": f"{lon:.6f}",
        "format": "jsonv2",
        "addressdetails": 1,
        "zoom": 18,
        "accept-language": "en",
    })
    if not isinstance(payload, dict):
        raise GeocodingError("The address service returned an invalid response.")
    display_name = str(payload.get("display_name", ""))
    within_city = is_bengaluru_address(payload.get("address", {}), display_name)
    if not within_city:
        return _outside_result(lat, lon)
    address = payload.get("address", {})
    label = str(
        payload.get("name")
        or address.get("amenity")
        or address.get("road")
        or address.get("neighbourhood")
        or address.get("suburb")
        or "Selected point"
    )
    return {
        "within_bengaluru": True,
        "label": label,
        "display_name": display_name,
        "lat": lat,
        "lon": lon,
    }


def require_bengaluru_point(lat: float, lon: float) -> dict[str, Any]:
    result = reverse_bengaluru(lat, lon)
    if not result["within_bengaluru"]:
        raise LocationOutsideBengaluru(result["message"])
    return result


def _outside_result(lat: float, lon: float) -> dict[str, Any]:
    return {
        "within_bengaluru": False,
        "label": "Outside Bengaluru",
        "display_name": "",
        "lat": lat,
        "lon": lon,
        "message": "This route finder is currently available only in Bengaluru. Select a point within Bengaluru.",
    }


def _nominatim(path: str, params: dict[str, Any]) -> Any:
    global _last_request
    base_url = os.getenv("NOMINATIM_BASE_URL", _BASE_URL).rstrip("/")
    url = f"{base_url}{path}?{urlencode(params)}"
    now = time.monotonic()
    with _lock:
        cached = _cache.get(url)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            _cache.move_to_end(url)
            return cached[1]
        delay = _MIN_REQUEST_INTERVAL - (now - _last_request)
        if delay > 0:
            time.sleep(delay)
        _last_request = time.monotonic()
        request = Request(url, headers={
            "Accept": "application/json",
            "User-Agent": os.getenv("NOMINATIM_USER_AGENT", _USER_AGENT),
        })
        try:
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GeocodingError(f"The address service returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise GeocodingError("The address service is temporarily unavailable.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GeocodingError("The address service returned an unreadable response.") from exc
        _cache[url] = (time.monotonic(), payload)
        _cache.move_to_end(url)
        while len(_cache) > _CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)
        return payload
