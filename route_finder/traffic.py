"""Bengaluru traffic congestion model, hotspot detection, and intelligent traffic-aware rerouting."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from .graph import haversine_km

TrafficMode = Literal["normal", "peak", "offpeak"]

# Static planning cautions requested for monsoon mode. These are not a live flood feed.
FLOOD_RISK_POINTS: list[dict[str, Any]] = [
    {
        "id": "ecospace-underpass",
        "name": "Ecospace underpass",
        "lat": 12.9267,
        "lon": 77.6765,
        "radius_km": 0.45,
        "description": "Static monsoon caution area; verify local conditions before travel.",
    },
    {
        "id": "windsor-manor-underpass",
        "name": "Windsor Manor underpass",
        "lat": 12.9845,
        "lon": 77.5908,
        "radius_km": 0.4,
        "description": "Static monsoon caution area; verify local conditions before travel.",
    },
    {
        "id": "hebbal-underpass",
        "name": "Hebbal underpass",
        "lat": 13.0400,
        "lon": 77.5930,
        "radius_km": 0.5,
        "description": "Static monsoon caution area; verify local conditions before travel.",
    },
]


@dataclass(frozen=True)
class TrafficHotspot:
    id: str
    name: str
    lat: float
    lon: float
    radius_km: float
    severity: Literal["moderate", "heavy", "severe"]
    base_delay_multiplier: float  # e.g., 2.5 means travel time through this zone takes 2.5x
    description: str


# Well-known chronic traffic corridors & choke points across Bengaluru
BENGALURU_TRAFFIC_HOTSPOTS: list[TrafficHotspot] = [
    TrafficHotspot(
        id="silk_board",
        name="Central Silk Board Junction",
        lat=12.9176,
        lon=77.6238,
        radius_km=1.2,
        severity="severe",
        base_delay_multiplier=3.2,
        description="Major intersection connecting Hosur Road, BTM, and Outer Ring Road.",
    ),
    TrafficHotspot(
        id="bellandur_ecospace",
        name="Bellandur / Ecospace (ORR)",
        lat=12.9260,
        lon=77.6762,
        radius_km=1.4,
        severity="severe",
        base_delay_multiplier=2.9,
        description="Tech corridor choke point along Outer Ring Road with heavy commuter queues.",
    ),
    TrafficHotspot(
        id="tin_factory",
        name="Tin Factory & KR Puram Bridge",
        lat=12.9982,
        lon=77.6685,
        radius_km=1.2,
        severity="heavy",
        base_delay_multiplier=2.6,
        description="Bottleneck convergence of Old Madras Road, railway station, and ORR.",
    ),
    TrafficHotspot(
        id="hebbal_flyover",
        name="Hebbal Flyover Junction",
        lat=13.0358,
        lon=77.5970,
        radius_km=1.3,
        severity="heavy",
        base_delay_multiplier=2.5,
        description="North Bengaluru and Kempegowda Airport highway merge point.",
    ),
    TrafficHotspot(
        id="marathahalli",
        name="Marathahalli Multiplex / Bridge",
        lat=12.9554,
        lon=77.7011,
        radius_km=1.1,
        severity="heavy",
        base_delay_multiplier=2.4,
        description="High-density connector between HAL Old Airport Road, Varthur, and Whitefield.",
    ),
    TrafficHotspot(
        id="sony_world",
        name="Sony World Junction, Koramangala",
        lat=12.9345,
        lon=77.6265,
        radius_km=0.8,
        severity="moderate",
        base_delay_multiplier=1.8,
        description="Major commercial intersection on 80 Feet Road / 100 Feet Road.",
    ),
    TrafficHotspot(
        id="goraguntepalya",
        name="Goraguntepalya / Yeshwantpur",
        lat=13.0285,
        lon=77.5407,
        radius_km=1.1,
        severity="heavy",
        base_delay_multiplier=2.2,
        description="Tumkur Road highway entrance and intercity bus terminal congestion.",
    ),
    TrafficHotspot(
        id="richmond_circle",
        name="Richmond Circle & Residency Road",
        lat=12.9665,
        lon=77.5990,
        radius_km=0.8,
        severity="moderate",
        base_delay_multiplier=1.7,
        description="Central Business District intersection with recurring signal cycles.",
    ),
    TrafficHotspot(
        id="dairy_circle",
        name="Dairy Circle & Bannerghatta Road",
        lat=12.9360,
        lon=77.5995,
        radius_km=0.9,
        severity="moderate",
        base_delay_multiplier=1.8,
        description="South Bengaluru arterial bottleneck leading toward Jayadeva and Bannerghatta.",
    ),
    TrafficHotspot(
        id="hope_farm",
        name="Hope Farm Junction, Whitefield",
        lat=12.9839,
        lon=77.7519,
        radius_km=1.0,
        severity="heavy",
        base_delay_multiplier=2.2,
        description="East Bengaluru tech hub nexus connecting Kadugodi, Channasandra, and ITPL.",
    ),
]


@dataclass
class RouteTrafficAnalysis:
    free_flow_min: float
    duration_with_traffic_min: float
    traffic_delay_min: float
    congestion_level: Literal["clear", "moderate", "heavy", "severe"]
    hotspots_detected: list[dict[str, Any]] = field(default_factory=list)
    congested_segments_km: float = 0.0


def get_mode_factor(mode: TrafficMode) -> float:
    """Modeled multiplier; this is a planning estimate, not a live traffic feed."""
    if mode == "peak":
        return 1.45  # Peak rush hour
    if mode == "offpeak":
        return 0.40  # Late night / Sunday early morning
    return 1.00  # Typical Bengaluru daytime traffic


def analyze_flood_risk(
    coordinates: list[tuple[float, float]],
    points: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return static flood-caution areas near a route; never implies current flooding."""
    if len(coordinates) < 2:
        return []
    risks = []
    for hazard in points if points is not None else FLOOD_RISK_POINTS:
        closest = min(
            haversine_km(
                ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2),
                (float(hazard["lat"]), float(hazard["lon"])),
            )
            for a, b in zip(coordinates, coordinates[1:])
        )
        if closest <= float(hazard["radius_km"]):
            risks.append({**hazard, "distance_km": round(closest, 2)})
    return risks


def analyze_route_traffic(
    coordinates: list[tuple[float, float]],
    free_flow_duration_min: float,
    mode: TrafficMode = "normal",
    hotspots: list[TrafficHotspot] | None = None,
) -> RouteTrafficAnalysis:
    """Analyze a polyline against known Bengaluru traffic hotspots.

    Calculates the proportion of the route running through congestion zones
    and adds realistic time delays.
    """
    if len(coordinates) < 2 or free_flow_duration_min <= 0:
        return RouteTrafficAnalysis(
            free_flow_min=free_flow_duration_min,
            duration_with_traffic_min=free_flow_duration_min,
            traffic_delay_min=0.0,
            congestion_level="clear",
            hotspots_detected=[],
            congested_segments_km=0.0,
        )

    mode_factor = get_mode_factor(mode)
    zones = hotspots if hotspots is not None else BENGALURU_TRAFFIC_HOTSPOTS

    # Calculate total path length
    segment_lengths = [
        haversine_km(coordinates[i], coordinates[i + 1])
        for i in range(len(coordinates) - 1)
    ]
    total_km = sum(segment_lengths)
    if total_km <= 0.01:
        return RouteTrafficAnalysis(
            free_flow_min=free_flow_duration_min,
            duration_with_traffic_min=free_flow_duration_min,
            traffic_delay_min=0.0,
            congestion_level="clear",
            hotspots_detected=[],
            congested_segments_km=0.0,
        )

    base_min_per_km = free_flow_duration_min / total_km
    total_delay_min = 0.0
    detected_zones: dict[str, dict[str, Any]] = {}
    congested_km = 0.0

    # Inspect each segment against traffic zones
    for i, seg_km in enumerate(segment_lengths):
        p1 = coordinates[i]
        p2 = coordinates[i + 1]
        mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)

        worst_multiplier = 1.0
        worst_hotspot: TrafficHotspot | None = None

        for spot in zones:
            dist = haversine_km(mid, (spot.lat, spot.lon))
            if dist <= spot.radius_km:
                # Proximity weight: higher delay near the epicenter
                proximity = max(0.2, 1.0 - (dist / spot.radius_km) * 0.7)
                effective_mult = 1.0 + (spot.base_delay_multiplier - 1.0) * proximity * mode_factor
                if effective_mult > worst_multiplier:
                    worst_multiplier = effective_mult
                    worst_hotspot = spot

        if worst_hotspot is not None and worst_multiplier > 1.05:
            congested_km += seg_km
            seg_base_time = seg_km * base_min_per_km
            seg_delay = seg_base_time * (worst_multiplier - 1.0)
            total_delay_min += seg_delay

            if worst_hotspot.id not in detected_zones:
                detected_zones[worst_hotspot.id] = {
                    "id": worst_hotspot.id,
                    "name": worst_hotspot.name,
                    "lat": worst_hotspot.lat,
                    "lon": worst_hotspot.lon,
                    "severity": worst_hotspot.severity,
                    "description": worst_hotspot.description,
                    "delay_min": 0.0,
                }
            detected_zones[worst_hotspot.id]["delay_min"] += seg_delay

    # Determine overall congestion level
    if total_delay_min < 2.0:
        congestion_level = "clear"
    elif total_delay_min < 8.0:
        congestion_level = "moderate"
    elif total_delay_min < 16.0:
        congestion_level = "heavy"
    else:
        congestion_level = "severe"

    hotspots_list = sorted(
        detected_zones.values(),
        key=lambda item: item["delay_min"],
        reverse=True,
    )
    for spot in hotspots_list:
        spot["delay_min"] = round(spot["delay_min"], 1)

    duration_with_traffic = free_flow_duration_min + total_delay_min

    return RouteTrafficAnalysis(
        free_flow_min=round(free_flow_duration_min, 1),
        duration_with_traffic_min=round(duration_with_traffic, 1),
        traffic_delay_min=round(total_delay_min, 1),
        congestion_level=congestion_level,
        hotspots_detected=hotspots_list,
        congested_segments_km=round(congested_km, 2),
    )


def compute_avoidance_waypoint(
    start: tuple[float, float],
    destination: tuple[float, float],
    hotspot: dict[str, Any],
) -> tuple[float, float]:
    """Compute a smart lateral detour waypoint to steer the routing engine around a bottleneck.

    Generates a point perpendicular to the line connecting start and destination,
    pushed outside the congestion radius.
    """
    h_lat, h_lon = float(hotspot["lat"]), float(hotspot["lon"])
    s_lat, s_lon = start
    d_lat, d_lon = destination

    dx = d_lon - s_lon
    dy = d_lat - s_lat
    mag = math.hypot(dx, dy)
    if mag < 1e-5:
        return (h_lat + 0.02, h_lon + 0.02)

    # Unit vector perpendicular to start -> destination line
    perp_x = -dy / mag
    perp_y = dx / mag

    # Detour distance ~2.2 km away from hotspot center (outside the 1.2-1.4 km radius)
    offset_deg = 0.025  # ~2.5 to 2.8 km in Bengaluru coordinates

    # Choose detour side that doesn't push way outside the city
    cand1 = (h_lat + perp_y * offset_deg, h_lon + perp_x * offset_deg)
    cand2 = (h_lat - perp_y * offset_deg, h_lon - perp_x * offset_deg)

    # Pick candidate closest to Bengaluru center (12.9716, 77.5946) to remain on viable roads
    bengaluru_center = (12.9716, 77.5946)
    if haversine_km(cand1, bengaluru_center) <= haversine_km(cand2, bengaluru_center):
        return cand1
    return cand2
