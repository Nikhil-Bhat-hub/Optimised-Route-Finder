"""OpenStreetMap network loading via OSMnx (downloaded and cached on request)."""
from __future__ import annotations
from pathlib import Path
import os
import time
from .graph import RoadGraph

BENGALURU = (12.9716, 77.5946)

def load_bengaluru_graph(
    place: str | None = None,
    cache_path: str | None = None,
    retries: int = 3,
) -> RoadGraph:
    try:
        import osmnx as ox
    except ImportError as exc:
        raise RuntimeError("Install optional dependency osmnx to download the Bengaluru road network") from exc
    place = place or os.getenv("ROUTE_PLACE", "Bengaluru, Karnataka, India")
    cache_path = cache_path or os.getenv("GRAPH_PATH", "data/bengaluru.graphml")
    path = Path(cache_path); path.parent.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.overpass_rate_limit = True
    ox.settings.requests_timeout = 180
    if path.exists():
        network = ox.load_graphml(path)
    else:
        last_error = None
        for attempt in range(max(1, retries)):
            try:
                network = ox.graph_from_place(place, network_type="drive", simplify=True)
                ox.save_graphml(network, path)
                break
            except Exception as exc:
                last_error = exc
                if attempt + 1 < max(1, retries):
                    time.sleep(1.5 * (2 ** attempt))
        else:
            raise RuntimeError(
                "OpenStreetMap's public Overpass service is temporarily unavailable. "
                "The app can use its built-in Bengaluru demo network for now; "
                "retry the live map later. Details: " + str(last_error)
            ) from last_error
    graph = RoadGraph()
    for node, data in network.nodes(data=True): graph.add_node(str(node), data.get("y", 0), data.get("x", 0))
    for u, v, data in network.edges(data=True):
        distance = float(data.get("length", 0)) / 1000
        speed = float(data.get("speed_kph", 30) or 30)
        graph.add_edge(str(u), str(v), distance, speed, bidirectional=False)
    return graph


def demo_bengaluru_graph() -> RoadGraph:
    """Small, clearly labeled fallback graph so the UI works during Overpass outages."""
    places = {
        "Majestic": (12.9767, 77.5713),
        "Cubbon Park": (12.9763, 77.5929),
        "MG Road": (12.9756, 77.6066),
        "Bangalore Palace": (12.9987, 77.5928),
        "Lalbagh": (12.9507, 77.5848),
        "Koramangala": (12.9352, 77.6245),
        "Indiranagar": (12.9784, 77.6408),
        "Whitefield": (12.9698, 77.7500),
    }
    links = [
        ("Majestic", "Cubbon Park", 2.8, 24),
        ("Cubbon Park", "MG Road", 1.9, 22),
        ("Cubbon Park", "Bangalore Palace", 3.1, 30),
        ("Majestic", "Lalbagh", 4.1, 25),
        ("Lalbagh", "Koramangala", 6.3, 28),
        ("Koramangala", "MG Road", 5.6, 24),
        ("MG Road", "Indiranagar", 5.4, 27),
        ("Indiranagar", "Whitefield", 13.2, 35),
        ("Bangalore Palace", "Indiranagar", 8.2, 30),
        ("Majestic", "Bangalore Palace", 4.2, 26),
    ]
    graph = RoadGraph()
    for name, (lat, lon) in places.items():
        graph.add_node(name, lat, lon)
    for start, end, distance, speed in links:
        graph.add_edge(start, end, distance, speed)
    return graph
