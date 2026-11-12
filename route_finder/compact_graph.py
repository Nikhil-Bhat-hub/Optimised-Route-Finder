"""Portable gzip graph format for the Render free instance."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from .graph import RoadGraph

MAX_COMPACT_GRAPH_BYTES = 30 * 1024 * 1024
FORMAT_VERSION = 1


def save_compact_graph(graph: RoadGraph, path: str | Path) -> int:
    """Serialize a directed graph with numeric edge indexes and deterministic gzip."""
    node_ids = sorted(graph.coordinates)
    index = {node_id: position for position, node_id in enumerate(node_ids)}
    payload: dict[str, Any] = {
        "version": FORMAT_VERSION,
        "nodes": [
            [node_id, graph.coordinates[node_id][0], graph.coordinates[node_id][1]]
            for node_id in node_ids
        ],
        "edges": [
            [index[source], index[target], edge[0], edge[1]]
            for source in node_ids
            for target, edge in graph.adj.get(source, {}).items()
        ],
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as compressed:
            compressed.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    size = output.stat().st_size
    if size > MAX_COMPACT_GRAPH_BYTES:
        output.unlink(missing_ok=True)
        raise ValueError(f"Compact road graph is {size / 1024 / 1024:.1f} MiB; limit is 30 MiB.")
    return size


def load_compact_graph(path: str | Path, max_bytes: int = MAX_COMPACT_GRAPH_BYTES) -> RoadGraph:
    """Load the checked-in compact graph and reject malformed or oversized files."""
    source = Path(path)
    size = source.stat().st_size
    if size <= 0 or size > max_bytes:
        raise ValueError(f"Compact graph file size is outside the allowed range: {size} bytes.")
    with gzip.open(source, "rt", encoding="utf-8") as compressed:
        payload = json.load(compressed)
    if payload.get("version") != FORMAT_VERSION:
        raise ValueError("Unsupported compact road graph version.")
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not nodes or not isinstance(edges, list):
        raise ValueError("Compact road graph is missing nodes or edges.")
    graph = RoadGraph()
    for node in nodes:
        node_id, lat, lon = node
        graph.add_node(str(node_id), float(lat), float(lon))
    for source_index, target_index, distance_km, duration_min in edges:
        if not (0 <= source_index < len(nodes) and 0 <= target_index < len(nodes)):
            raise ValueError("Compact road graph contains an invalid edge index.")
        distance_km = float(distance_km)
        duration_min = float(duration_min)
        if distance_km < 0 or duration_min <= 0:
            continue
        speed_kph = distance_km / duration_min * 60
        if speed_kph <= 0:
            continue
        graph.add_edge(
            str(nodes[source_index][0]),
            str(nodes[target_index][0]),
            distance_km,
            speed_kph,
            bidirectional=False,
        )
    return graph
