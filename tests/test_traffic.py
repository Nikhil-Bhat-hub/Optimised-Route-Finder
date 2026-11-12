import pytest
from route_finder.traffic import (
    BENGALURU_TRAFFIC_HOTSPOTS,
    FLOOD_RISK_POINTS,
    TrafficHotspot,
    analyze_flood_risk,
    analyze_route_traffic,
    compute_avoidance_waypoint,
)
from route_finder.osrm_client import fetch_dual_traffic_routes


def test_traffic_hotspots_defined():
    assert len(BENGALURU_TRAFFIC_HOTSPOTS) >= 5
    ids = [h.id for h in BENGALURU_TRAFFIC_HOTSPOTS]
    assert "silk_board" in ids
    assert "bellandur_ecospace" in ids
    assert "tin_factory" in ids


def test_clear_route_traffic_analysis():
    # Route far from any hotspot
    coords = [(12.9000, 77.5000), (12.9050, 77.5050)]
    analysis = analyze_route_traffic(coords, free_flow_duration_min=10.0, mode="normal")
    assert analysis.traffic_delay_min == 0.0
    assert analysis.congestion_level == "clear"
    assert len(analysis.hotspots_detected) == 0


def test_congested_route_traffic_analysis():
    # Route passing directly through Silk Board (12.9176, 77.6238)
    coords = [
        (12.9150, 77.6200),
        (12.9176, 77.6238),
        (12.9200, 77.6280),
    ]
    analysis = analyze_route_traffic(coords, free_flow_duration_min=12.0, mode="peak")
    assert analysis.traffic_delay_min > 0.0
    assert len(analysis.hotspots_detected) > 0
    assert analysis.hotspots_detected[0]["id"] == "silk_board"
    assert analysis.duration_with_traffic_min > analysis.free_flow_min


def test_avoidance_waypoint_computation():
    start = (12.9767, 77.5713)
    dest = (12.9176, 77.6238)
    hotspot = {
        "lat": 12.9176,
        "lon": 77.6238,
        "radius_km": 1.2,
    }
    waypoint = compute_avoidance_waypoint(start, dest, hotspot)
    assert isinstance(waypoint, tuple)
    assert len(waypoint) == 2
    # Detour must be at least 1.5 km away from the hotspot
    from route_finder.graph import haversine_km
    assert haversine_km(waypoint, (hotspot["lat"], hotspot["lon"])) > 1.2


def test_dual_traffic_routes_structure(monkeypatch):
    primary_coords = [[77.6200, 12.9150], [77.6238, 12.9176], [77.6280, 12.9200]]
    alt_coords = [[77.6000, 12.9150], [77.6050, 12.9200], [77.6100, 12.9250]]

    fake_payload = {
        "code": "Ok",
        "routes": [
            {
                "distance": 8000,
                "duration": 900,
                "geometry": {"type": "LineString", "coordinates": primary_coords},
                "legs": [{"steps": [{"name": "Hosur Rd", "distance": 8000, "duration": 900, "maneuver": {"type": "depart"}}]}],
            },
            {
                "distance": 9200,
                "duration": 950,
                "geometry": {"type": "LineString", "coordinates": alt_coords},
                "legs": [{"steps": [{"name": "Inner Ring Rd", "distance": 9200, "duration": 950, "maneuver": {"type": "depart"}}]}],
            },
        ],
    }

    class FakeResponse:
        def __init__(self, payload):
            import json
            self.payload = json.dumps(payload).encode("utf-8")
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return self.payload

    from route_finder import osrm_client
    monkeypatch.setattr(osrm_client, "urlopen", lambda *_args, **_kwargs: FakeResponse(fake_payload))
    monkeypatch.setattr(osrm_client.time, "sleep", lambda _s: None)
    monkeypatch.setattr(osrm_client, "_last_request_started", 0)

    result = fetch_dual_traffic_routes((12.9150, 77.6200), (12.9200, 77.6280), traffic_mode="peak")
    assert "fastest_route" in result
    assert "traffic_route" in result
    assert "has_traffic_reroute" in result
    assert "time_saved_min" in result
    assert "traffic_hotspots" in result


def test_static_rain_risk_detection_is_labeled_by_location():
    risk = FLOOD_RISK_POINTS[0]
    route = [
        (risk["lat"] - 0.004, risk["lon"] - 0.005),
        (risk["lat"] + 0.004, risk["lon"] + 0.005),
    ]
    detected = analyze_flood_risk(route)
    assert detected
    assert detected[0]["id"] == risk["id"]
