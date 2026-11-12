"""Small open-path TSP optimizer for a fixed start and destination."""
from __future__ import annotations

from collections.abc import Sequence
import math


def optimize_stop_order(durations: Sequence[Sequence[float]]) -> tuple[list[int], float]:
    """Use nearest-neighbor initialization and 2-opt while keeping endpoints fixed.

    Matrix indexes 0 and n-1 are the fixed start and destination. Returned indexes
    describe the full journey, including every intermediate waypoint exactly once.
    """
    count = len(durations)
    if count < 2 or any(len(row) != count for row in durations):
        raise ValueError("A square duration matrix with at least two points is required.")
    if any(not math.isfinite(float(value)) or float(value) < 0 for row in durations for value in row):
        raise ValueError("Travel durations must be finite and non-negative.")

    destination = count - 1
    remaining = set(range(1, destination))
    order = [0]
    while remaining:
        current = order[-1]
        next_stop = min(remaining, key=lambda node: float(durations[current][node]))
        order.append(next_stop)
        remaining.remove(next_stop)
    order.append(destination)

    improved = True
    while improved:
        improved = False
        current_cost = _path_cost(order, durations)
        for left in range(1, len(order) - 2):
            for right in range(left + 1, len(order) - 1):
                candidate = order[:left] + list(reversed(order[left : right + 1])) + order[right + 1 :]
                candidate_cost = _path_cost(candidate, durations)
                if candidate_cost + 1e-9 < current_cost:
                    order = candidate
                    current_cost = candidate_cost
                    improved = True
    return order, round(_path_cost(order, durations), 2)


def _path_cost(order: Sequence[int], durations: Sequence[Sequence[float]]) -> float:
    return sum(float(durations[a][b]) for a, b in zip(order, order[1:]))
