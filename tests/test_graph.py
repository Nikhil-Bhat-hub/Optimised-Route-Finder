import pytest
from route_finder.graph import RoadGraph, haversine_km

@pytest.fixture
def graph():
    g=RoadGraph(); g.add_edge("A","B",1,30); g.add_edge("B","C",1,30); g.add_edge("A","C",3,60); g.add_node("Z"); return g

def test_weighted_algorithms_choose_shortest_path(graph):
    for method in (graph.dijkstra,graph.astar):
        result=method("A","C")
        assert result.nodes==["A","B","C"]
        assert result.distance_km==pytest.approx(2)

def test_time_metric_uses_travel_time(graph):
    result=graph.dijkstra("A","C","time")
    assert result.nodes==["A","C"]
    assert result.duration_min==pytest.approx(3)

def test_bfs_and_dfs_return_valid_paths(graph):
    for result in (graph.bfs("A","C"),graph.dfs("A","C")):
        assert result.nodes[0]=="A" and result.nodes[-1]=="C"

def test_missing_and_disconnected_nodes(graph):
    assert graph.dijkstra("A","Z") is None
    assert graph.bfs("unknown","A") is None

def test_invalid_edge_rejected():
    with pytest.raises(ValueError): RoadGraph().add_edge("A","B",-1)

def test_haversine():
    assert haversine_km((0,0),(0,1))==pytest.approx(111.195,rel=0.002)
