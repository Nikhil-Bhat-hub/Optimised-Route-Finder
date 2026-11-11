"""Streamlit UI for the Optimised Route Finder."""
from __future__ import annotations

import os
import time
import networkx as nx
import osmnx as ox
import pandas as pd
import plotly.express as px
import streamlit as st
import folium
from streamlit_folium import st_folium

from algorithms.astar import astar_path
from algorithms.bfs import bfs_path
from algorithms.dfs import dfs_path
from algorithms.dijkstra import dijkstra_path
from backend.map_data import load_graph, nearest_node, route_coordinates, route_metrics
from database.database import init_db, save_route, get_recent_routes

st.set_page_config(page_title="Optimised Route Finder", page_icon="🗺️", layout="wide")
DEFAULT_PLACE = os.getenv("ROUTE_PLACE", "Bengaluru, Karnataka, India")
GRAPH_PATH = os.getenv("GRAPH_PATH", "data/bengaluru.graphml")

@st.cache_resource(show_spinner="Loading the road network…")
def get_road_graph():
    return load_graph(place=DEFAULT_PLACE, graph_path=GRAPH_PATH)


def make_map(graph, routes, selected):
    fmap = folium.Map(location=[12.9716, 77.5946], zoom_start=12, control_scale=True)
    palette = {"Dijkstra": "blue", "A*": "green", "BFS": "purple", "DFS": "orange"}
    first_coords = None
    for name, path in routes.items():
        coords = route_coordinates(graph, path)
        if not coords:
            continue
        first_coords = first_coords or coords
        folium.PolyLine(coords, color=palette.get(name, "blue"), weight=7 if name == selected else 4,
                        opacity=0.9 if name == selected else 0.55, tooltip=name).add_to(fmap)
    if first_coords:
        folium.Marker(first_coords[0], tooltip="Start", icon=folium.Icon(color="darkgreen", icon="play")).add_to(fmap)
        folium.Marker(first_coords[-1], tooltip="Destination", icon=folium.Icon(color="red", icon="flag")).add_to(fmap)
    return fmap


init_db()
st.title("🗺️ Optimised Route Finder")
st.caption("Compare graph algorithms on real OpenStreetMap road networks.")
with st.sidebar:
    st.header("Route settings")
    optimization = st.radio("Optimize for", ["Shortest distance", "Fastest estimated time"])
    algorithms_selected = st.multiselect("Algorithms", ["Dijkstra", "A*", "BFS", "DFS"], default=["Dijkstra", "A*"])
    st.divider()
    st.caption(f"Road network: {DEFAULT_PLACE}")
    st.caption("Estimated travel time is based on road speed metadata, not live traffic.")

try:
    graph = get_road_graph()
except Exception as exc:
    st.error(f"Could not load the road network: {exc}")
    st.info("Check internet access and run `python scripts/download_graph.py` first.")
    st.stop()

with st.form("route_form"):
    c1, c2 = st.columns(2)
    start_text = c1.text_input("Starting location", "Indian Institute of Science, Bengaluru")
    end_text = c2.text_input("Destination", "Cubbon Park, Bengaluru")
    submitted = st.form_submit_button("Find optimized routes", type="primary", use_container_width=True)

if submitted:
    if not algorithms_selected:
        st.warning("Select at least one algorithm.")
    else:
        try:
            with st.spinner("Looking up locations and calculating routes…"):
                start_lat, start_lon = ox.geocode(start_text)
                end_lat, end_lon = ox.geocode(end_text)
                source = nearest_node(graph, start_lat, start_lon)
                target = nearest_node(graph, end_lat, end_lon)
                weight = "length" if optimization == "Shortest distance" else "travel_time"
                solvers = {
                    "Dijkstra": lambda: dijkstra_path(graph, source, target, weight),
                    "A*": lambda: astar_path(graph, source, target, weight),
                    "BFS": lambda: bfs_path(graph, source, target),
                    "DFS": lambda: dfs_path(graph, source, target),
                }
                routes, rows = {}, []
                for name in algorithms_selected:
                    started = time.perf_counter()
                    try:
                        path, explored = solvers[name]()
                        elapsed = (time.perf_counter() - started) * 1000
                        routes[name] = path
                        metrics = route_metrics(graph, path)
                        rows.append({"Algorithm": name, "Distance (km)": metrics["distance_m"] / 1000,
                                     "Estimated time (min)": metrics["travel_time_s"] / 60,
                                     "Nodes in path": len(path), "Nodes explored": explored,
                                     "Execution time (ms)": elapsed,
                                     "Optimality": "Optimal for selected weights" if name in ("Dijkstra", "A*") else "Not guaranteed"})
                    except (nx.NetworkXNoPath, nx.NodeNotFound, ValueError) as err:
                        st.warning(f"{name}: no route found ({err})")
                if routes:
                    df = pd.DataFrame(rows)
                    sort_col = "Distance (km)" if weight == "length" else "Estimated time (min)"
                    selected = df.sort_values(sort_col).iloc[0]["Algorithm"]
                    st.session_state.update(routes=routes, route_rows=rows, selected_route=selected)
                    chosen = next(row for row in rows if row["Algorithm"] == selected)
                    save_route(start_text, end_text, optimization, selected, chosen["Distance (km)"], chosen["Estimated time (min)"], chosen["Execution time (ms)"])
                else:
                    st.error("No route could be found for the selected algorithms.")
        except Exception as exc:
            st.error(f"Route calculation failed: {exc}")
            st.caption("Location lookup requires access to OpenStreetMap Nominatim.")

if "routes" in st.session_state:
    route_names = list(st.session_state.routes)
    selected = st.selectbox("Highlight route", route_names, index=route_names.index(st.session_state.selected_route))
    st.session_state.selected_route = selected
    row = next(r for r in st.session_state.route_rows if r["Algorithm"] == selected)
    m1, m2, m3 = st.columns(3)
    m1.metric("Distance", f"{row['Distance (km)']:.2f} km")
    m2.metric("Estimated time", f"{row['Estimated time (min)']:.1f} min")
    m3.metric("Nodes explored", f"{row['Nodes explored']:,}")
    st.subheader("Route map")
    st_folium(make_map(graph, st.session_state.routes, selected), use_container_width=True, height=540)
    st.subheader("Algorithm comparison")
    df = pd.DataFrame(st.session_state.route_rows)
    st.dataframe(df.round(3), use_container_width=True, hide_index=True)
    a, b = st.columns(2)
    a.plotly_chart(px.bar(df, x="Algorithm", y="Execution time (ms)", title="Execution time"), use_container_width=True)
    b.plotly_chart(px.bar(df, x="Algorithm", y="Nodes explored", title="Nodes explored"), use_container_width=True)
    st.info("BFS and DFS are unweighted traversal baselines. They do not guarantee the shortest-distance or fastest route.")

with st.expander("Recent route searches"):
    history = get_recent_routes()
    if history:
        st.dataframe(pd.DataFrame(history, columns=["ID", "From", "To", "Optimization", "Algorithm", "Distance (km)", "Time (min)", "Execution (ms)", "Created"]), use_container_width=True, hide_index=True)
    else:
        st.caption("No routes saved yet.")
st.divider()
st.caption("© OpenStreetMap contributors. Travel times are estimates, not live traffic predictions.")
