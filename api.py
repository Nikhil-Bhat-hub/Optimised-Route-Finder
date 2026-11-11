"""FastAPI endpoints for route lookup and route history."""
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv
from route_finder.osm import load_bengaluru_graph
from route_finder.storage import RouteHistory

load_dotenv()
app=FastAPI(title="Optimised Route Finder API", version="1.0.0")
class RouteRequest(BaseModel): source: str; target: str; metric: str="distance"
def graph():
    try: return load_bengaluru_graph()
    except Exception as exc: raise HTTPException(503, str(exc))
@app.get("/health")
def health(): return {"status":"ok"}
@app.post("/routes")
def routes(request: RouteRequest):
    if request.metric not in ("distance","time"): raise HTTPException(422,"metric must be distance or time")
    network=graph(); results=[]
    for method in ("dijkstra","astar","bfs","dfs"):
        route=getattr(network,method)(request.source,request.target,request.metric) if method in ("dijkstra","astar") else getattr(network,method)(request.source,request.target)
        if route:
            RouteHistory().save(request.source,request.target,request.metric,route)
            results.append({"algorithm":route.algorithm,"nodes":route.nodes,"distance_km":route.distance_km,"duration_min":route.duration_min,"elapsed_ms":route.elapsed_ms})
    return {"source":request.source,"target":request.target,"metric":request.metric,"routes":results}
@app.get("/history")
def history(limit: int=Query(50,ge=1,le=500)): return RouteHistory().recent(limit)
