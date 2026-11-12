"""Modern Streamlit interface for the Bengaluru Optimised Route Finder with live traffic analysis."""
from __future__ import annotations

import os

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
from dotenv import load_dotenv

from route_finder.graph import haversine_km
from route_finder.osm import demo_bengaluru_graph, load_bengaluru_graph
from route_finder.osrm_client import OSRMRouteError, fetch_dual_traffic_routes
from route_finder.storage import RouteHistory
from route_finder.traffic import BENGALURU_TRAFFIC_HOTSPOTS

load_dotenv()


st.set_page_config(
    page_title="Routewise · Bengaluru (Traffic Aware)",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { --ink:#172b36; --muted:#70818a; --teal:#087e79; --teal-dark:#08645f; --mint:#e5f4ef; --paper:#f5f7f6; --line:#e3e9e7; }
.stApp { background:var(--paper); color:var(--ink); font-family:'DM Sans',sans-serif; }
header[data-testid="stHeader"] { background:rgba(245,247,246,.94); }
section[data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); }
section[data-testid="stSidebar"] > div { padding-top:1.5rem; }
.block-container { max-width:1500px; padding-top:1.6rem; padding-bottom:3rem; }
h1,h2,h3 { font-family:'Manrope',sans-serif !important; color:var(--ink) !important; letter-spacing:-.035em; }
h1 { font-size:2.7rem !important; font-weight:800 !important; }
h2 { font-size:1.55rem !important; font-weight:750 !important; }
p, label, span { font-family:'DM Sans',sans-serif; }
.brand { color:var(--teal); font-size:.82rem; letter-spacing:.14em; text-transform:uppercase; font-weight:700; }
.hero { background:linear-gradient(118deg,#123b43 0%,#0a6c68 65%,#118e7e 100%); border-radius:24px; padding:32px 36px; color:white; margin:.55rem 0 1.25rem; box-shadow:0 16px 42px rgba(17,73,72,.15); }
.hero h1 { color:white !important; margin:.35rem 0 .45rem; }
.hero p { color:#d5eeeb; margin:0; font-size:1rem; }
.hero-tag { display:inline-block; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.2); border-radius:999px; padding:6px 11px; color:#e6fbf5; font-size:.76rem; font-weight:700; letter-spacing:.04em; }
.panel { background:#fff; border:1px solid var(--line); border-radius:20px; padding:22px 24px; box-shadow:0 5px 20px rgba(26,54,62,.035); }
.section-kicker { color:var(--teal); text-transform:uppercase; letter-spacing:.12em; font-weight:700; font-size:.72rem; margin-bottom:4px; }
.route-title { color:#20343c; font-family:'Manrope',sans-serif; font-weight:750; font-size:1.22rem; }
.caption { color:var(--muted); font-size:.91rem; }
.status-pill { display:inline-flex; align-items:center; gap:7px; border-radius:99px; padding:7px 11px; font-size:.78rem; font-weight:700; }
.status-live { background:#e5f4eb; color:#236b44; }
.status-demo { background:#fff3dd; color:#8b5c08; }
.traffic-alert { background:#ecfdf5; border:1px solid #a7f3d0; border-radius:12px; padding:12px 16px; margin:10px 0; color:#065f46; font-size:.95rem; }
div[data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:16px; padding:14px 16px; }
div[data-testid="stMetricLabel"] { color:#74848a; }
div[data-testid="stMetricValue"] { color:var(--ink); font-family:'Manrope',sans-serif; }
div.stButton > button[kind="primary"] { background:var(--teal); border:0; border-radius:12px; min-height:3rem; font-weight:700; box-shadow:0 7px 17px rgba(8,126,121,.17); }
div.stButton > button[kind="primary"]:hover { background:var(--teal-dark); border:0; }
div.stButton > button { border-radius:11px; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:14px; overflow:hidden; }
div[data-testid="stAlert"] { border-radius:14px; }
footer { visibility:hidden; }
@media(max-width:800px) { .hero { padding:25px 22px; border-radius:18px; } h1 { font-size:2.05rem !important; } .block-container { padding-left:1rem; padding-right:1rem; } }
</style>
""", unsafe_allow_html=True)


@st.cache_resource(ttl=900, show_spinner="Preparing Bengaluru road network…")
def get_network():
    try:
        return load_bengaluru_graph(), "live", None
    except Exception as exc:
        return demo_bengaluru_graph(), "demo", str(exc)


@st.cache_data(ttl=900, max_entries=128, show_spinner=False)
def get_dual_live_routes(start: tuple[float, float], end: tuple[float, float], traffic_mode: str, service_url: str):
    return fetch_dual_traffic_routes(start, end, traffic_mode=traffic_mode, base_url=service_url)


if st.sidebar.button("↻  Retry live road data", use_container_width=True):
    get_network.clear()
    st.session_state.pop("routes", None)
    st.session_state.pop("route_pair", None)
    st.session_state.pop("traffic_data", None)
    st.session_state.pop("osrm_error", None)
    st.rerun()

graph, network_mode, network_error = get_network()
LANDMARKS = {
    "Majestic": (12.9767, 77.5713),
    "Cubbon Park": (12.9763, 77.5929),
    "MG Road": (12.9756, 77.6066),
    "Bangalore Palace": (12.9987, 77.5928),
    "Lalbagh": (12.9507, 77.5848),
    "Koramangala": (12.9352, 77.6245),
    "Indiranagar": (12.9784, 77.6408),
    "Whitefield": (12.9698, 77.7500),
}
places = sorted(LANDMARKS)
if network_mode == "demo":
    place_nodes = {name: name for name in places}
else:
    place_nodes = {
        name: min(graph.coordinates, key=lambda node: haversine_km(LANDMARKS[name], graph.coordinates[node]))
        for name in places
    }

st.markdown('<div class="brand">ROUTEWISE&nbsp;&nbsp; / &nbsp;&nbsp;BENGALURU</div>', unsafe_allow_html=True)
st.markdown("""
<div class="hero">
  <span class="hero-tag">TRAFFIC-AWARE INTELLIGENT ROUTING</span>
  <h1>Find your fastest route.</h1>
  <p>Detect road congestion bottlenecks, automatically calculate bypass routes, and compare classic algorithms.</p>
</div>
""", unsafe_allow_html=True)

pill_class = "status-live" if network_mode == "live" else "status-demo"
pill_text = "LIVE OSM NETWORK & TRAFFIC MONITOR" if network_mode == "live" else "DEMO ALGORITHMS · LIVE OSRM & TRAFFIC"
st.markdown(f'<span class="status-pill {pill_class}">● &nbsp;{pill_text}</span>', unsafe_allow_html=True)
if network_mode == "demo":
    st.info("Algorithm comparisons are using an illustrative Bengaluru network. Live road routing & traffic analysis remain active through OSRM.")

with st.sidebar:
    st.markdown("### Plan a route")
    st.caption("Choose two Bengaluru locations and traffic conditions.")
    source = st.selectbox("FROM", places, index=0)
    destination_options = [place for place in places if place != source] or places
    target = st.selectbox("TO", destination_options, index=min(2, len(destination_options) - 1))
    traffic_choice = st.radio("TRAFFIC MODEL", ["Normal / Day", "Peak Rush Hour", "Off-Peak Night"], horizontal=True)
    traffic_mode = "peak" if "Peak" in traffic_choice else ("offpeak" if "Off-Peak" in traffic_choice else "normal")
    metric = st.radio("OPTIMISE FOR", ["Distance", "Travel time"], horizontal=True)
    metric_key = "time" if metric == "Travel time" else "distance"
    find_route = st.button("Find best routes  →", type="primary", use_container_width=True)
    st.markdown("---")
    st.caption("**Monitored Bottlenecks**")
    st.caption(f"{len(BENGALURU_TRAFFIC_HOTSPOTS)} active choke points (Silk Board, Ecospace ORR, Tin Factory, Hebbal, etc.)")


if find_route:
    found = []
    source_node, target_node = place_nodes[source], place_nodes[target]
    for method in ("dijkstra", "astar", "bfs", "dfs"):
        route = (getattr(graph, method)(source_node, target_node, metric_key)
                 if method in ("dijkstra", "astar")
                 else getattr(graph, method)(source_node, target_node))
        if route:
            RouteHistory().save(source, target, metric_key, route)
            found.append(route)
    st.session_state["routes"] = found
    st.session_state["route_pair"] = (source, target)
    st.session_state["route_metric"] = metric_key
    try:
        service_url = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
        st.session_state["traffic_data"] = get_dual_live_routes(
            LANDMARKS[source], LANDMARKS[target], traffic_mode, service_url
        )
        st.session_state["osrm_error"] = None
    except OSRMRouteError as exc:
        st.session_state["traffic_data"] = None
        st.session_state["osrm_error"] = str(exc)

routes = st.session_state.get("routes", [])
route_pair = st.session_state.get("route_pair")
route_matches_selection = (
    route_pair == (source, target)
    and st.session_state.get("route_metric") == metric_key
)
shown_routes = routes if route_matches_selection else []
traffic_data = (
    st.session_state.get("traffic_data")
    if route_pair == (source, target)
    else None
)
osrm_error = (
    st.session_state.get("osrm_error")
    if route_pair == (source, target)
    else None
)

if traffic_data:
    fastest = traffic_data["fastest_route"]
    traffic = traffic_data["traffic_route"]

    if traffic_data.get("has_traffic_reroute"):
        st.markdown(f"""
        <div class="traffic-alert">
          <strong>⚡ Dynamic Traffic Rerouting Active:</strong> {traffic_data['reroute_reason']}
        </div>
        """, unsafe_allow_html=True)

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("FASTEST (TRAFFIC AVOIDED)", f"{fastest['duration_min']:.0f} min", delta=f"-{traffic_data['time_saved_min']:.0f} min saved" if traffic_data['has_traffic_reroute'] else "Optimal")
    t2.metric("FASTEST DISTANCE", f"{fastest['distance_km']:.1f} km")
    t3.metric("ROUTE WITH TRAFFIC", f"{traffic['duration_min']:.0f} min", delta=f"+{traffic['traffic_delay_min']:.0f} min delay" if traffic.get('traffic_delay_min', 0) > 0 else "Normal")
    t4.metric("TRAFFIC DISTANCE", f"{traffic['distance_km']:.1f} km")

elif osrm_error:
    st.warning(f"Live road routing is temporarily unavailable. {osrm_error} The local route comparison is still available.")


left, right = st.columns([.85, 1.45], gap="large")
with left:
    st.markdown('<div class="section-kicker">ROUTE OPTIONS</div>', unsafe_allow_html=True)
    st.markdown("## Compare paths")
    st.markdown('<div class="caption">Dual traffic routing compared against classic Dijkstra, A*, BFS, and DFS.</div>', unsafe_allow_html=True)
    if shown_routes:
        table = [{
            "Algorithm": route.algorithm,
            "Distance": f"{route.distance_km:.2f} km",
            "Drive time": f"{route.duration_min:.0f} min",
            "Nodes explored": getattr(route, "nodes_explored", 0),
            "Search (ms)": f"{route.elapsed_ms:.2f}",
        } for route in shown_routes]
        st.dataframe(table, use_container_width=True, hide_index=True)
    else:
        st.markdown('<div class="panel"><div class="section-kicker">READY WHEN YOU ARE</div><div class="route-title">Your route comparison will appear here.</div><div class="caption">Pick your start and destination in the sidebar, then select Find best routes.</div></div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="section-kicker">CITY MAP</div>', unsafe_allow_html=True)
    st.markdown("## Bengaluru, live route & traffic view")
    center = (12.9716, 77.5946)
    if traffic_data:
        coords = traffic_data["fastest_route"]["coordinates"]
        if coords:
            center = coords[len(coords) // 2]
    city_map = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap", control_scale=True)

    if traffic_data:
        fastest_coords = traffic_data["fastest_route"]["coordinates"]
        traffic_coords = traffic_data["traffic_route"]["coordinates"]

        # Route with traffic: Coral Red
        folium.PolyLine(
            traffic_coords,
            color="#dc2626",
            weight=4,
            opacity=0.7,
            dash_array="6, 6",
            tooltip=f"Route with Traffic · {traffic_data['traffic_route']['duration_min']:.0f} min",
        ).add_to(city_map)

        # Fastest route (avoids traffic): Emerald Green
        folium.PolyLine(
            fastest_coords,
            color="#059669",
            weight=6,
            opacity=0.95,
            tooltip=f"Fastest Route (Traffic Avoided) · {traffic_data['fastest_route']['duration_min']:.0f} min",
        ).add_to(city_map)

        # Bottleneck warning markers
        for spot in traffic_data.get("traffic_hotspots", []):
            folium.Marker(
                [spot["lat"], spot["lon"]],
                tooltip=f"⚠️ {spot['name']} ({spot['severity'].upper()})",
                icon=folium.Icon(color="red", icon="warning-sign", prefix="glyphicon"),
            ).add_to(city_map)

        folium.Marker(fastest_coords[0], tooltip=f"Start · {source}", icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(city_map)
        folium.Marker(fastest_coords[-1], tooltip=f"Destination · {target}", icon=folium.Icon(color="red", icon="flag", prefix="fa")).add_to(city_map)
        city_map.fit_bounds(fastest_coords + traffic_coords, padding=(30, 30))
    else:
        folium.CircleMarker(center, radius=8, color="#087e79", fill=True, tooltip="Bengaluru").add_to(city_map)

    st_folium(city_map, height=520, use_container_width=True, returned_objects=[])
    st.caption("Map data © OpenStreetMap contributors · Solid green: fastest route avoiding traffic · Dashed red: route with traffic choke points.")

st.markdown("---")
history = RouteHistory().recent(50)
analytics, recent_searches = st.columns([1, 1], gap="large")
with analytics:
    st.markdown('<div class="section-kicker">PERFORMANCE</div>', unsafe_allow_html=True)
    st.markdown("## Search speed")
    if history:
        frame = pd.DataFrame(history)
        average = frame.groupby("algorithm")["elapsed_ms"].mean().sort_values()
        st.bar_chart(average, y_label="Average search time (ms)")
    else:
        st.caption("Search performance will appear after your first route.")
with recent_searches:
    st.markdown('<div class="section-kicker">YOUR ACTIVITY</div>', unsafe_allow_html=True)
    st.markdown("## Recent searches")
    if history:
        st.dataframe([{
            "From": row["source"], "To": row["target"], "Algorithm": row["algorithm"],
            "Distance": f'{row["distance_km"]:.1f} km', "Time": f'{row["duration_min"]:.0f} min',
        } for row in history[:8]], use_container_width=True, hide_index=True)
    else:
        st.caption("Your saved route searches will show up here.")

st.markdown("<div style='text-align:center;color:#8a989d;font-size:.8rem;padding:2rem 0 0'>ROUTEWISE · BUILT FOR BENGALURU · ROUTING & TRAFFIC BY OSRM · MAP DATA © OPENSTREETMAP CONTRIBUTORS</div>", unsafe_allow_html=True)
