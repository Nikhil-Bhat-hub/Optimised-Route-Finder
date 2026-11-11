from route_finder.graph import RoadGraph
from route_finder.storage import RouteHistory

def test_history_round_trip(tmp_path):
    g=RoadGraph(); g.add_edge("A","B",1)
    result=g.dijkstra("A","B")
    store=RouteHistory(tmp_path/"routes.db")
    store.save("A","B","distance",result)
    row=store.recent()[0]
    assert row["source"]=="A" and row["target"]=="B"
    assert row["distance_km"]==1 and row["nodes_json"]=='["A", "B"]'
