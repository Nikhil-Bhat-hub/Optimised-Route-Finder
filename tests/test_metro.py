from route_finder.metro import BMRCL_TIMINGS_URL, STATIONS, estimate_metro


def test_metro_estimate_is_available_for_purple_line_trip():
    result = estimate_metro(
        STATIONS["Whitefield"],
        STATIONS["Nadaprabhu Kempegowda Station, Majestic"],
    )
    assert result["available"] is True
    assert result["estimated_duration_min"] > result["train_duration_min"]
    assert result["start_station"] == "Whitefield"
    assert result["schedule_url"] == BMRCL_TIMINGS_URL
