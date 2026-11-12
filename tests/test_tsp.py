import pytest

from route_finder.tsp import optimize_stop_order


def test_optimizer_keeps_endpoints_and_improves_visit_order():
    matrix = [
        [0, 2, 8, 9, 0],
        [2, 0, 2, 8, 5],
        [8, 2, 0, 2, 2],
        [9, 8, 2, 0, 2],
        [0, 5, 2, 2, 0],
    ]
    order, duration = optimize_stop_order(matrix)

    assert order[0] == 0
    assert order[-1] == 4
    assert set(order[1:-1]) == {1, 2, 3}
    assert duration == pytest.approx(sum(matrix[a][b] for a, b in zip(order, order[1:])))
    assert duration <= 14


def test_optimizer_rejects_non_square_matrix():
    with pytest.raises(ValueError, match="square"):
        optimize_stop_order([[0, 2], [3]])
