from route_finder.compact_graph import load_compact_graph, save_compact_graph
from route_finder.graph import RoadGraph


def test_compact_graph_round_trip_preserves_coords_and_costs(tmp_path):
    graph = RoadGraph()
    graph.add_node("A", 12.97, 77.57)
    graph.add_node("B", 12.98, 77.58)
    graph.add_edge("A", "B", 1.4, 28, bidirectional=False)
    path = tmp_path / "compact.json.gz"

    size = save_compact_graph(graph, path)
    loaded = load_compact_graph(path)

    assert size == path.stat().st_size
    assert loaded.coordinates["A"] == (12.97, 77.57)
    assert loaded.dijkstra("A", "B").distance_km == 1.4
    assert loaded.dijkstra("B", "A") is None
