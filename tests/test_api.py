import asyncio

import api as route_api


def test_stop_order_api_uses_osrm_matrix_and_returns_order(monkeypatch):
    def fake_validate(lat, lon):
        return {"within_bengaluru": True, "label": "Bengaluru"}

    async def fake_matrix(_points, base_url=None):
        return [
            [0, 2, 7, 6],
            [2, 0, 2, 4],
            [7, 2, 0, 2],
            [6, 4, 2, 0],
        ]

    monkeypatch.setattr(route_api, "require_bengaluru_point", fake_validate)
    monkeypatch.setattr(route_api, "async_fetch_osrm_duration_matrix", fake_matrix)
    request = route_api.OptimizeOrderRequest(points=[
        route_api.RoutePoint(lat=12.97, lon=77.57, label="Start"),
        route_api.RoutePoint(lat=12.98, lon=77.58, label="Stop A"),
        route_api.RoutePoint(lat=12.96, lon=77.59, label="Stop B"),
        route_api.RoutePoint(lat=12.95, lon=77.60, label="Destination"),
    ])

    result = asyncio.run(route_api.route_optimize_order(request))

    assert result["points"][0]["label"] == "Start"
    assert result["points"][-1]["label"] == "Destination"
    assert {point["label"] for point in result["points"][1:-1]} == {"Stop A", "Stop B"}
    assert result["estimated_drive_min"] > 0
