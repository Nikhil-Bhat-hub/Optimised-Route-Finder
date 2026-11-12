"""Weighted road graph, classic pathfinding algorithms, and a compact spatial index."""
from __future__ import annotations

import heapq
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class RouteResult:
    algorithm: str
    nodes: list[str]
    distance_km: float
    duration_min: float
    elapsed_ms: float
    nodes_explored: int = 0
    visited_order: list[str] = field(default_factory=list)
    explored_edges: list[tuple[str, str]] = field(default_factory=list)


class KDTree:
    """Balanced 2D index for fast nearest-road snapping inside a city-sized area."""

    def __init__(self, coordinates: dict[str, tuple[float, float]]):
        self._longitude_scale = math.cos(math.radians(
            sum(point[0] for point in coordinates.values()) / max(1, len(coordinates))
        ))
        self._root = self._build(list(coordinates.items()), depth=0)

    def _axis_value(self, point: tuple[float, float], axis: int) -> float:
        return point[0] if axis == 0 else point[1] * self._longitude_scale

    def _build(self, items: list[tuple[str, tuple[float, float]]], depth: int):
        if not items:
            return None
        axis = depth % 2
        items.sort(key=lambda item: self._axis_value(item[1], axis))
        middle = len(items) // 2
        node_id, point = items[middle]
        return (
            node_id,
            point,
            axis,
            self._build(items[:middle], depth + 1),
            self._build(items[middle + 1 :], depth + 1),
        )

    def nearest(self, point: tuple[float, float]) -> tuple[str, float]:
        if self._root is None:
            raise ValueError("Cannot snap a point to an empty graph.")
        query = (point[0], point[1] * self._longitude_scale)
        best: tuple[str, tuple[float, float], float] | None = None

        def visit(node):
            nonlocal best
            if node is None:
                return
            node_id, candidate, axis, left, right = node
            projected = (candidate[0], candidate[1] * self._longitude_scale)
            distance_squared = (query[0] - projected[0]) ** 2 + (query[1] - projected[1]) ** 2
            if best is None or distance_squared < best[2]:
                best = (node_id, candidate, distance_squared)
            delta = query[axis] - projected[axis]
            near, far = (left, right) if delta < 0 else (right, left)
            visit(near)
            if delta * delta <= (best[2] if best else math.inf):
                visit(far)

        visit(self._root)
        assert best is not None
        return best[0], haversine_km(point, best[1])


class RoadGraph:
    def __init__(self):
        self.adj: dict[str, dict[str, tuple[float, float]]] = {}
        self.coordinates: dict[str, tuple[float, float]] = {}
        self._spatial_index: KDTree | None = None

    def add_node(self, node: str, lat: float = 0.0, lon: float = 0.0) -> None:
        node = str(node)
        self.adj.setdefault(node, {})
        self.coordinates[node] = (float(lat), float(lon))
        self._spatial_index = None

    def add_edge(
        self,
        a: str,
        b: str,
        distance_km: float,
        speed_kph: float = 30.0,
        bidirectional: bool = True,
    ) -> None:
        if distance_km < 0 or speed_kph <= 0:
            raise ValueError("Distance must be non-negative and speed must be positive")
        if str(a) not in self.adj:
            self.add_node(a)
        if str(b) not in self.adj:
            self.add_node(b)
        edge = (float(distance_km), float(distance_km) / float(speed_kph) * 60)
        self.adj[str(a)][str(b)] = edge
        if bidirectional:
            self.adj[str(b)][str(a)] = edge

    def nearest_node(self, point: tuple[float, float]) -> tuple[str, float]:
        if self._spatial_index is None:
            self._spatial_index = KDTree(self.coordinates)
        return self._spatial_index.nearest(point)

    def _route(
        self,
        source: str,
        target: str,
        cost: Callable[[tuple[float, float]], float],
        heuristic: Callable[[str], float] = lambda _: 0.0,
        algorithm: str = "Dijkstra",
    ) -> RouteResult | None:
        source, target = str(source), str(target)
        if source not in self.adj or target not in self.adj:
            return None
        start = time.perf_counter()
        frontier = [(heuristic(source), 0.0, source)]
        best = {source: 0.0}
        parent: dict[str, str] = {}
        settled = set()
        visited_order: list[str] = []
        explored_edges: list[tuple[str, str]] = []

        while frontier:
            _, score, node = heapq.heappop(frontier)
            if node in settled:
                continue
            settled.add(node)
            visited_order.append(node)
            if node == target:
                break
            for neighbor, edge in self.adj[node].items():
                candidate = score + cost(edge)
                if candidate < best.get(neighbor, math.inf):
                    best[neighbor] = candidate
                    parent[neighbor] = node
                    explored_edges.append((node, neighbor))
                    heapq.heappush(frontier, (candidate + heuristic(neighbor), candidate, neighbor))

        elapsed = (time.perf_counter() - start) * 1000
        if target not in best:
            return None
        path = [target]
        while path[-1] != source:
            path.append(parent[path[-1]])
        path.reverse()
        distance = sum(self.adj[a][b][0] for a, b in zip(path, path[1:]))
        duration = sum(self.adj[a][b][1] for a, b in zip(path, path[1:]))
        return RouteResult(
            algorithm, path, distance, duration, elapsed, len(visited_order),
            _sample(visited_order, 240), _sample(explored_edges, 360),
        )

    def dijkstra(self, source: str, target: str, metric: str = "distance") -> RouteResult | None:
        return self._route(source, target, lambda e: e[0] if metric == "distance" else e[1], algorithm="Dijkstra")

    def astar(self, source: str, target: str, metric: str = "distance") -> RouteResult | None:
        source, target = str(source), str(target)
        if target not in self.coordinates:
            return self._route(source, target, lambda e: e[0] if metric == "distance" else e[1], algorithm="A*")
        max_speed = max(
            (distance / minutes * 60 for edges in self.adj.values()
             for distance, minutes in edges.values() if minutes > 0),
            default=0,
        )

        def estimate(node: str) -> float:
            straight = haversine_km(self.coordinates.get(node, (0.0, 0.0)), self.coordinates[target])
            return straight if metric == "distance" else (straight / max_speed * 60 if max_speed > 0 else 0.0)

        return self._route(source, target, lambda e: e[0] if metric == "distance" else e[1], estimate, "A*")

    def _unweighted(self, source: str, target: str, depth_first: bool = False) -> RouteResult | None:
        source, target = str(source), str(target)
        if source not in self.adj or target not in self.adj:
            return None
        start = time.perf_counter()
        frontier = [source] if depth_first else deque([source])
        parent: dict[str, str | None] = {source: None}
        visited_order: list[str] = []
        explored_edges: list[tuple[str, str]] = []

        while frontier:
            node = frontier.pop() if depth_first else frontier.popleft()
            visited_order.append(node)
            if node == target:
                break
            for other in self.adj[node]:
                if other not in parent:
                    parent[other] = node
                    explored_edges.append((node, other))
                    frontier.append(other)

        elapsed = (time.perf_counter() - start) * 1000
        if target not in parent:
            return None
        path = [target]
        while path[-1] is not None:
            path.append(parent[path[-1]])
        path = list(reversed(path[:-1]))
        return RouteResult(
            "DFS" if depth_first else "BFS",
            path,
            sum(self.adj[a][b][0] for a, b in zip(path, path[1:])),
            sum(self.adj[a][b][1] for a, b in zip(path, path[1:])),
            elapsed,
            len(visited_order),
            _sample(visited_order, 240),
            _sample(explored_edges, 360),
        )

    def bfs(self, source: str, target: str) -> RouteResult | None:
        return self._unweighted(source, target)

    def dfs(self, source: str, target: str) -> RouteResult | None:
        return self._unweighted(source, target, True)


def _sample(values: list, maximum: int) -> list:
    if len(values) <= maximum:
        return values
    stride = math.ceil(len(values) / maximum)
    sampled = values[::stride]
    return sampled if sampled[-1] == values[-1] else sampled + [values[-1]]


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))
