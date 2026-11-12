from route_finder import geocoding


def test_bengaluru_bounds_accept_city_and_reject_outside():
    assert geocoding.is_inside_bengaluru_bounds(12.9716, 77.5946)
    assert not geocoding.is_inside_bengaluru_bounds(12.2958, 76.6394)  # Mysuru


def test_bengaluru_address_accepts_city_or_district_names():
    assert geocoding.is_bengaluru_address({"city": "Bengaluru"})
    assert geocoding.is_bengaluru_address({"county": "Bangalore Urban"})
    assert not geocoding.is_bengaluru_address({"city": "Mysuru"})


def test_search_keeps_only_bengaluru_results(monkeypatch):
    results = [
        {
            "lat": "12.9352",
            "lon": "77.6245",
            "name": "Koramangala",
            "display_name": "Koramangala, Bengaluru, Karnataka, India",
            "address": {"city": "Bengaluru"},
        },
        {
            "lat": "12.2958",
            "lon": "76.6394",
            "name": "Mysuru",
            "display_name": "Mysuru, Karnataka, India",
            "address": {"city": "Mysuru"},
        },
    ]
    monkeypatch.setattr(geocoding, "_nominatim", lambda *_args: results)

    found = geocoding.search_bengaluru("Koramangala")

    assert len(found) == 1
    assert found[0]["label"] == "Koramangala"


def test_outside_result_explains_city_limit():
    result = geocoding._outside_result(12.2958, 76.6394)

    assert result["within_bengaluru"] is False
    assert "only in Bengaluru" in result["message"]
