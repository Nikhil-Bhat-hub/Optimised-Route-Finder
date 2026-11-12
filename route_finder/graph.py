"""Weighted road graph and classic shortest path algorithms."""
from __future__ import annotations

import heapq
import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable


@dataclass
class RouteResult:
    algorithm: str
    nodes: list[str]
    distance_km: float
    duration_min: float
    elapsed_ms: float
    nodes_explored: int = 0


class RoadGraph:
    def __init__(self):
        self.adj: dict[str, dict[str, tuple[float, float]]] = {}
        self.coordinates: dict[str, tuple[float, float]] = {}

    def add_node(self, node: str, lat: float = 0.0, lon: float = 0.0) -> None:
        self.adj.setdefault(str(node), {})
        self.coordinates[str(node)] = (float(lat), float(lon))

    def add_edge(self, a: str, b: str, distance_km: float, speed_kph: float = 30.0, bidirectional: bool = True) -> None:
        if distance_km < 0 or speed_kph <= 0:
            raise ValueError("Distance must be non-negative and speed must be positive")
        self.add_node(a); self.add_node(b)
        edge = (float(distance_km), float(distance_km) / float(speed_kph) * 60)
        self.adj[str(a)][str(b)] = edge
        if bidirectional:
            self.adj[str(b)][str(a)] = edge

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
        parent = {}
        settled = set()
        nodes_explored = 0

        while frontier:
            _, score, node = heapq.heappop(frontier)
            if node in settled:
                continue
            settled.add(node)
            nodes_explored += 1
            if node == target:
                break
            for neighbor, edge in self.adj[node].items():
                candidate = score + cost(edge)
                if candidate < best.get(neighbor, math.inf):
                    best[neighbor] = candidate
                    parent[neighbor] = node
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
        return RouteResult(algorithm, path, distance, duration, elapsed, nodes_explored)

    def dijkstra(self, source: str, target: str, metric: str = "distance") -> RouteResult | None:
        return self._route(source, target, lambda e: e[0] if metric == "distance" else e[1], algorithm="Dijkstra")

    def astar(self, source: str, target: str, metric: str = "distance") -> RouteResult | None:
        source, target = str(source), str(target)
        if target not in self.coordinates:
            return self._route(source, target, lambda e: e[0] if metric == "distance" else e[1], algorithm="A*")
        max_speed = max((distance / minutes * 60 for edges in self.adj.values()
                         for distance, minutes in edges.values() if minutes > 0), default=0)

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
        parent = {source: None}
        nodes_explored = 0

        while frontier:
            node = frontier.pop() if depth_first else frontier.popleft()
            nodes_explored += 1
            if node == target:
                break
            for other in self.adj[node]:
                if other not in parent:
                    parent[other] = node
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
            nodes_explored,
        )

    def bfs(self, source: str, target: str) -> RouteResult | None:
        return self._unweighted(source, target)

    def dfs(self, source: str, target: str) -> RouteResult | None:
        return self._unweighted(source, target, True)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))
