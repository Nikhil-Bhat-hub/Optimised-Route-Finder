"""Build the compact, major-road Bengaluru graph used by the hosted service."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import osmnx as ox

from route_finder.compact_graph import save_compact_graph
from route_finder.graph import RoadGraph

BENGALURU_BBOX = (77.40, 12.72, 77.86, 13.18)  # west, south, east, north
DEFAULT_OVERPASS_URLS = (
    "https://maps.mail.ru/osm/tools/overpass/api",
    "https://overpass.private.coffee/api",
    "https://overpass-api.de/api",
)
MAJOR_ROAD_FILTER = (
    '["highway"~"motorway|motorway_link|trunk|trunk_link|primary|primary_link|'
    'secondary|secondary_link|tertiary|tertiary_link|unclassified|residential"]'
)


def build(output_path: Path) -> tuple[int, int, int]:
    ox.settings.use_cache = True
    ox.settings.overpass_rate_limit = True
    ox.settings.requests_timeout = 300
    configured_urls = os.getenv("OVERPASS_URLS", "").strip()
    overpass_urls = tuple(
        url.strip().rstrip("/")
        for url in configured_urls.split(",")
        if url.strip()
    ) or DEFAULT_OVERPASS_URLS
    errors: list[str] = []
    road_network = None
    for endpoint in overpass_urls:
        ox.settings.overpass_url = endpoint
        # The VK Maps instance explicitly permits unrestricted requests and does
        # not need OSMnx's slot-management probe before sending a query.
        ox.settings.overpass_rate_limit = not endpoint.startswith(
            "https://maps.mail.ru/osm/tools/overpass/api"
        )
        print(f"Requesting Bengaluru road data from {endpoint}...", flush=True)
        try:
            road_network = ox.graph.graph_from_bbox(
                BENGALURU_BBOX,
                network_type="drive",
                simplify=True,
                retain_all=False,
                truncate_by_edge=True,
                custom_filter=MAJOR_ROAD_FILTER,
            )
            break
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
            print(
                f"Overpass endpoint failed; trying the next configured endpoint. ({exc})",
                file=sys.stderr,
                flush=True,
            )
    if road_network is None:
        raise RuntimeError(
            "All configured Overpass endpoints failed: " + " | ".join(errors)
        )
    road_network = ox.routing.add_edge_speeds(road_network)
    graph = RoadGraph()
    for node_id, data in road_network.nodes(data=True):
        graph.add_node(str(node_id), float(data["y"]), float(data["x"]))
    for start, end, data in road_network.edges(data=True):
        length_m = float(data.get("length", 0) or 0)
        speed_kph = float(data.get("speed_kph", 30) or 30)
        if length_m <= 0 or speed_kph <= 0:
            continue
        graph.add_edge(
            str(start),
            str(end),
            length_m / 1000,
            speed_kph,
            bidirectional=False,
        )
    if len(graph.coordinates) < 300 or sum(map(len, graph.adj.values())) < 1000:
        raise RuntimeError("The downloaded road graph is unexpectedly small; refusing to publish it.")
    size = save_compact_graph(graph, output_path)
    return len(graph.coordinates), sum(map(len, graph.adj.values())), size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/bengaluru-compact.json.gz"),
        help="Output path for the gzip graph (must be under 30 MiB).",
    )
    args = parser.parse_args()
    node_count, directed_edges, size = build(args.output)
    print(
        f"Built {node_count:,} Bengaluru road nodes and {directed_edges:,} directed edges "
        f"({size / 1024 / 1024:.2f} MiB) at {args.output}."
    )


if __name__ == "__main__":
    main()
