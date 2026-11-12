import json

import pytest

from route_finder import osrm_client


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_fetch_osrm_route_uses_lon_lat_and_converts_geojson(monkeypatch):
    requested = []
    payload = {
        "code": "Ok",
        "routes": [{
            "distance": 1250,
            "duration": 300,
            "geometry": {"type": "LineString", "coordinates": [[77.57, 12.97], [77.60, 12.98]]},
            "legs": [{"steps": [
                {"name": "Main Road", "distance": 500, "duration": 60,
                 "maneuver": {"type": "depart"}},
                {"name": "Market Street", "distance": 700, "duration": 180,
                 "maneuver": {"type": "turn", "modifier": "left"}},
                {"name": "", "distance": 50, "duration": 10,
                 "maneuver": {"type": "arrive"}},
            ]}],
        }],
    }

    def fake_urlopen(request, timeout):
        requested.append((request.full_url, timeout, request.get_header("User-agent")))
        return FakeResponse(payload)

    monkeypatch.setattr(osrm_client, "urlopen", fake_urlopen)
    monkeypatch.setattr(osrm_client.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(osrm_client, "_last_request_started", 0)

    result = osrm_client.fetch_osrm_route(
        (12.9767, 77.5713), (12.9756, 77.6066), "https://routing.example.test"
    )

    assert "/route/v1/driving/77.571300,12.976700;77.606600,12.975600?" in requested[0][0]
    assert requested[0][1] == 15
    assert requested[0][2].startswith("RoutewiseBengaluru/")
    assert result["distance_km"] == 1.25
    assert result["duration_min"] == 5
    assert result["coordinates"] == [(12.97, 77.57), (12.98, 77.60)]
    assert result["instructions"][0]["instruction"] == "Head toward Main Road"
    assert result["instructions"][1]["instruction"] == "Turn left onto Market Street"
    assert result["instructions"][-1]["instruction"] == "Arrive at your destination"


def test_fetch_osrm_route_reports_missing_road_route(monkeypatch):
    monkeypatch.setattr(osrm_client, "urlopen", lambda *_args, **_kwargs: FakeResponse({"code": "NoRoute"}))
    monkeypatch.setattr(osrm_client.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(osrm_client, "_last_request_started", 0)

    with pytest.raises(osrm_client.OSRMRouteError, match="No drivable route"):
        osrm_client.fetch_osrm_route((12.97, 77.57), (12.98, 77.60))
