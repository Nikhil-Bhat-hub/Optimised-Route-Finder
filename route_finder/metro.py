"""Indicative Namma Metro comparison using approximate station coordinates."""
from __future__ import annotations

from collections import deque

from .graph import haversine_km

BMRCL_TIMINGS_URL = "https://english.bmrc.co.in/metro-timings/"

# Approximate public station locations for an illustrative estimate. Timings are
# deliberately not treated as a live schedule or departure feed.
STATIONS = {
    "Whitefield": (12.9955, 77.7610),
    "Hopefarm Channasandra": (12.9891, 77.7512),
    "Kadugodi Tree Park": (12.9850, 77.7444),
    "Pattandur Agrahara": (12.9825, 77.7380),
    "Nallurhalli": (12.9808, 77.7300),
    "Kundalahalli": (12.9798, 77.7202),
    "Hoodi": (12.9917, 77.7137),
    "Garudacharpalya": (12.9950, 77.7050),
    "KR Puram": (13.0000, 77.6750),
    "Benniganahalli": (12.9985, 77.6610),
    "Baiyappanahalli": (12.9908, 77.6526),
    "Swami Vivekananda Road": (12.9854, 77.6446),
    "Indiranagar": (12.9784, 77.6408),
    "Halasuru": (12.9757, 77.6265),
    "Trinity": (12.9722, 77.6164),
    "MG Road": (12.9756, 77.6066),
    "Cubbon Park": (12.9763, 77.5929),
    "Dr. B. R. Ambedkar Station, Vidhana Soudha": (12.9791, 77.5907),
    "Sir M. Visvesvaraya Station": (12.9766, 77.5827),
    "Nadaprabhu Kempegowda Station, Majestic": (12.9767, 77.5713),
    "City Railway Station": (12.9761, 77.5622),
    "Magadi Road": (12.9758, 77.5553),
    "Vijayanagar": (12.9718, 77.5384),
    "Mysuru Road": (12.9523, 77.5294),
    "Kengeri": (12.9181, 77.4846),
    "Yeshwanthpur": (13.0238, 77.5511),
    "Sandal Soap Factory": (13.0102, 77.5550),
    "Mantri Square Sampige Road": (12.9913, 77.5703),
    "Chickpete": (12.9655, 77.5767),
    "Lalbagh": (12.9507, 77.5848),
    "Jayanagar": (12.9250, 77.5838),
    "Banashankari": (12.9152, 77.5736),
}

PURPLE_LINE = [
    "Whitefield", "Hopefarm Channasandra", "Kadugodi Tree Park", "Pattandur Agrahara",
    "Nallurhalli", "Kundalahalli", "Hoodi", "Garudacharpalya", "KR Puram",
    "Benniganahalli", "Baiyappanahalli", "Swami Vivekananda Road", "Indiranagar",
    "Halasuru", "Trinity", "MG Road", "Cubbon Park",
    "Dr. B. R. Ambedkar Station, Vidhana Soudha", "Sir M. Visvesvaraya Station",
    "Nadaprabhu Kempegowda Station, Majestic", "City Railway Station", "Magadi Road",
    "Vijayanagar", "Mysuru Road", "Kengeri",
]
GREEN_LINE = [
    "Yeshwanthpur", "Sandal Soap Factory", "Mantri Square Sampige Road",
    "Nadaprabhu Kempegowda Station, Majestic", "Chickpete", "Lalbagh", "Jayanagar",
    "Banashankari",
]


def estimate_metro(start: tuple[float, float], destination: tuple[float, float]) -> dict:
    start_station, start_walk = _nearest_station(start)
    end_station, end_walk = _nearest_station(destination)
    if start_station == end_station:
        stops = 0
        station_distance = 0.0
        station_path = [start_station]
    else:
        station_path, station_distance = _shortest_station_path(start_station, end_station)
        if not station_path:
            return {"available": False, "message": "No connected metro estimate is available for these points."}
        stops = max(0, len(station_path) - 1)

    walk_minutes = (start_walk + end_walk) / 4.5 * 60
    train_minutes = station_distance / 30.0 * 60 + max(0, stops - 1) * 0.75
    wait_minutes = 5.0
    total = round(walk_minutes + train_minutes + wait_minutes)
    return {
        "available": True,
        "estimated_duration_min": total,
        "walk_duration_min": round(walk_minutes),
        "train_duration_min": round(train_minutes),
        "assumed_wait_min": wait_minutes,
        "start_station": start_station,
        "destination_station": end_station,
        "stations": station_path,
        "transfer_count": _count_transfers(station_path),
        "source": "Illustrative estimate using approximate station locations and average speeds",
        "schedule_url": BMRCL_TIMINGS_URL,
    }


def _count_transfers(path: list[str]) -> int:
    edge_lines = {}
    for line_name, stations in (("Purple Line", PURPLE_LINE), ("Green Line", GREEN_LINE)):
        for a, b in zip(stations, stations[1:]):
            edge_lines[frozenset((a, b))] = line_name
    line_sequence = [edge_lines[frozenset((a, b))] for a, b in zip(path, path[1:])]
    return sum(previous != current for previous, current in zip(line_sequence, line_sequence[1:]))


def _nearest_station(point: tuple[float, float]) -> tuple[str, float]:
    return min(
        ((name, haversine_km(point, location)) for name, location in STATIONS.items()),
        key=lambda item: item[1],
    )


def _shortest_station_path(start: str, destination: str) -> tuple[list[str], float]:
    adjacency: dict[str, list[str]] = {station: [] for station in STATIONS}
    for stations in (PURPLE_LINE, GREEN_LINE):
        for a, b in zip(stations, stations[1:]):
            adjacency[a].append(b)
            adjacency[b].append(a)
    queue = deque([start])
    parent: dict[str, str | None] = {start: None}
    while queue:
        current = queue.popleft()
        if current == destination:
            break
        for neighbor in adjacency[current]:
            if neighbor not in parent:
                parent[neighbor] = current
                queue.append(neighbor)
    if destination not in parent:
        return [], 0.0
    path = [destination]
    while path[-1] is not None:
        path.append(parent[path[-1]])
    path = list(reversed(path[:-1]))
    distance = sum(haversine_km(STATIONS[a], STATIONS[b]) for a, b in zip(path, path[1:]))
    return path, distance
