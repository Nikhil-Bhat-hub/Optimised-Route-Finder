(() => {
  const BENGALURU = [12.9716, 77.5946];
  const state = {
    start: null,
    destination: null,
    waypoints: [],
    target: "start",
    optimize: "time",
    avoidFlood: false,
    activeRouteType: "fastest",
    fastestRoute: null,
    trafficRoute: null,
    markers: {},
    fastestLayer: null,
    trafficLayer: null,
    rainMarkers: [],
    trafficSectionsLayer: L.layerGroup(),
    searchLayers: L.layerGroup(),
    algorithmResults: [],
    explorationLayers: L.layerGroup(),
    explorationTimer: null,
    lastRouteData: null,
    toastTimer: null,
    searchSequence: 0,
  };

  const $ = (id) => document.getElementById(id);
  const map = L.map("map", { zoomControl: false, scrollWheelZoom: true }).setView(BENGALURU, 12);
  state.searchLayers.addTo(map);
  state.explorationLayers.addTo(map);
  state.trafficSectionsLayer.addTo(map);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>',
  }).addTo(map);

  const routeButton = $("routeButton");
  const searchInput = $("locationSearch");
  const notice = $("notice");
  const suggestions = $("suggestions");

  function showNotice(message, type = "info") {
    notice.textContent = message;
    notice.className = `notice${type === "info" ? "" : ` ${type}`}`;
    notice.hidden = false;
  }
  function hideNotice() { notice.hidden = true; }
  function showToast(message) {
    const toast = $("toast");
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => { toast.hidden = true; }, 5000);
  }

  async function api(path, options) {
    const response = await fetch(path, options);
    let body;
    try { body = await response.json(); } catch { body = {}; }
    if (!response.ok) {
      const detail = typeof body.detail === "string" ? body.detail : "The request could not be completed. Please try again.";
      throw new Error(detail);
    }
    return body;
  }

  function setTarget(target) {
    state.target = target;
    document.querySelectorAll("[data-target]").forEach((button) => {
      const active = button.dataset.target === target;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    const chip = $("targetChip");
    const isStart = target === "start";
    const isDestination = target === "destination";
    chip.innerHTML = `<i class="mini-dot ${isStart ? "a-dot" : isDestination ? "b-dot" : "stop-dot"}"></i> ${isStart ? "Start point" : isDestination ? "Destination" : `Stop ${Number(target.split("-")[1]) + 1}`}`;
  }

  function stopLabel(index) { return state.waypoints[index]?.label || `Stop ${index + 1} · choose on map`; }
  function allStopsReady() { return state.waypoints.every(Boolean); }
  function renderWaypoints() {
    const host = $("waypointsList");
    if (!host) return;
    host.replaceChildren();
    state.waypoints.forEach((point, index) => {
      const target = `stop-${index}`;
      const row = document.createElement("div");
      row.className = "waypoint-row";
      const bullet = document.createElement("span");
      bullet.className = "waypoint-bullet";
      bullet.textContent = String(index + 1);
      const name = document.createElement("span");
      name.className = "waypoint-name";
      name.textContent = point?.label || `Stop ${index + 1} · choose on map`;
      const choose = document.createElement("button");
      choose.type = "button";
      choose.textContent = point ? "Change" : "Set";
      choose.setAttribute("aria-label", `${point ? "Change" : "Set"} stop ${index + 1} on map`);
      choose.addEventListener("click", () => setTarget(target));
      row.append(bullet, name, choose);
      if (point) {
        const clear = document.createElement("button");
        clear.type = "button";
        clear.textContent = "×";
        clear.setAttribute("aria-label", `Remove stop ${index + 1}`);
        clear.addEventListener("click", () => removeWaypoint(index));
        row.append(clear);
      } else {
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "×";
        remove.setAttribute("aria-label", `Remove stop ${index + 1}`);
        remove.addEventListener("click", () => removeWaypoint(index));
        row.append(remove);
      }
      host.append(row);
    });
    $("optimizeStopsButton").disabled = state.waypoints.length === 0 || !state.start || !state.destination || !allStopsReady();
  }

  function removeWaypoint(index) {
    const markerKey = `stop-${index}`;
    if (state.markers[markerKey]) map.removeLayer(state.markers[markerKey]);
    delete state.markers[markerKey];
    state.waypoints.splice(index, 1);
    state.waypoints.forEach((point, i) => {
      const oldMarker = state.markers[`stop-${i + 1}`];
      if (oldMarker) map.removeLayer(oldMarker);
      delete state.markers[`stop-${i + 1}`];
    });
    state.waypoints.forEach((point, i) => { if (point) markerFor(`stop-${i}`, point); });
    updatePlanner();
    $("results").hidden = true;
  }

  function updatePlanner() {
    [["start", "startValue"], ["destination", "destinationValue"]].forEach(([key, id]) => {
      const value = $(id);
      value.textContent = state[key]?.label || "Choose a point";
      value.classList.toggle("is-set", Boolean(state[key]));
      document.querySelector(`[data-clear="${key}"]`).hidden = !state[key];
    });
    renderWaypoints();
    const ready = Boolean(state.start && state.destination && allStopsReady());
    routeButton.disabled = !ready;
    document.querySelector(".button-hint").textContent = ready ? "Ready to compare your route and estimates" : "Choose every stop, then set a start and destination";
    $("shareRouteButton").disabled = !ready;
    updateGoogleMapsLink();
  }

  function markerFor(target, point) {
    const css = target === "start" ? "start" : target === "destination" ? "destination" : "stop";
    const label = target === "start" ? "A" : target === "destination" ? "B" : String(Number(target.split("-")[1]) + 1);
    const icon = L.divIcon({
      className: "",
      html: `<div class="route-marker ${css}"><span>${label}</span></div>`,
      iconSize: [32, 36],
      iconAnchor: [16, 34],
    });
    if (state.markers[target]) {
      state.markers[target].setLatLng([point.lat, point.lon]).setIcon(icon).bindTooltip(point.label, { direction: "top", offset: [0, -27] });
    } else {
      state.markers[target] = L.marker([point.lat, point.lon], { icon, keyboard: true, title: point.label }).addTo(map).bindTooltip(point.label, { direction: "top", offset: [0, -27] });
    }
  }

  function addPoint(target, point) {
    const cleanPoint = { lat: Number(point.lat), lon: Number(point.lon), label: point.label || "Selected point" };
    if (target.startsWith("stop-")) state.waypoints[Number(target.split("-")[1])] = cleanPoint;
    else state[target] = cleanPoint;
    markerFor(target, cleanPoint);
    updatePlanner();
    hideNotice();
    $("results").hidden = true;
    if (state.start && state.destination) {
      const bounds = L.latLngBounds([[state.start.lat, state.start.lon], [state.destination.lat, state.destination.lon]]);
      map.fitBounds(bounds.pad(0.28), { maxZoom: 14, animate: true });
    } else {
      map.flyTo([point.lat, point.lon], Math.max(map.getZoom(), 14), { duration: 0.55 });
    }
  }

  async function chooseCoordinate(lat, lon, target = state.target) {
    showNotice("Checking this point is within Bengaluru…");
    try {
      const result = await api(`/api/locations/reverse?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
      if (!result.within_bengaluru) {
        showNotice("This route finder is available only in Bengaluru. Choose a point within the city boundary.", "warning");
        return;
      }
      addPoint(target, result);
      showNotice(`${target === "start" ? "Start" : target === "destination" ? "Destination" : "Stop"} set to ${result.label}.`, "info");
    } catch (error) {
      showNotice(error.message || "The address service is temporarily unavailable. Try searching again.", "error");
    }
  }
  map.on("click", (event) => { void chooseCoordinate(event.latlng.lat, event.latlng.lng); });

  function hideSuggestions() { suggestions.hidden = true; suggestions.replaceChildren(); }
  function renderSuggestions(results) {
    suggestions.replaceChildren();
    if (!results.length) {
      const empty = document.createElement("div");
      empty.className = "suggestion-empty";
      empty.textContent = "No Bengaluru matches. Try a neighbourhood, road, or landmark inside the city.";
      suggestions.append(empty);
      suggestions.hidden = false;
      return;
    }
    results.forEach((result) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "suggestion";
      button.setAttribute("role", "option");
      const icon = document.createElement("span");
      icon.className = "suggestion-icon";
      icon.textContent = "⌖";
      const copy = document.createElement("span");
      copy.className = "suggestion-copy";
      const title = document.createElement("strong");
      title.textContent = result.label;
      const detail = document.createElement("span");
      detail.textContent = result.display_name;
      copy.append(title, detail);
      button.append(icon, copy);
      button.addEventListener("click", () => {
        addPoint(state.target, result);
        searchInput.value = "";
        hideSuggestions();
        showNotice(`${state.target === "start" ? "Start" : state.target === "destination" ? "Destination" : "Stop"} set to ${result.label}.`, "info");
      });
      suggestions.append(button);
    });
    suggestions.hidden = false;
  }

  async function searchPlaces() {
    const query = searchInput.value.trim();
    if (query.length < 2) { hideSuggestions(); return; }
    const sequence = ++state.searchSequence;
    try {
      const data = await api(`/api/locations/search?q=${encodeURIComponent(query)}`);
      if (sequence === state.searchSequence) renderSuggestions(data.results || []);
    } catch (error) {
      hideSuggestions();
      showNotice(error.message || "Place search is temporarily unavailable.", "error");
    }
  }

  searchInput.addEventListener("input", hideSuggestions);
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); void searchPlaces(); }
    if (event.key === "Escape") hideSuggestions();
  });
  $("searchButton").addEventListener("click", () => { void searchPlaces(); });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".search-block")) hideSuggestions();
  });

  document.querySelectorAll("[data-target]").forEach((button) => button.addEventListener("click", () => setTarget(button.dataset.target)));

  document.querySelectorAll("[data-optimize]").forEach((button) => button.addEventListener("click", () => {
    state.optimize = button.dataset.optimize;
    document.querySelectorAll("[data-optimize]").forEach((item) => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
  }));

  document.querySelectorAll("[data-clear]").forEach((button) => button.addEventListener("click", () => {
    const key = button.dataset.clear;
    state[key] = null;
    if (state.markers[key]) { map.removeLayer(state.markers[key]); delete state.markers[key]; }
    updatePlanner();
    $("results").hidden = true;
    showNotice(`${key === "start" ? "Start" : "Destination"} cleared.`);
  }));

  function formatDistance(km) { return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`; }
  function formatDuration(minutes) { return minutes < 1 ? "< 1 min" : `${Math.round(minutes)} min`; }

  function renderAlgorithms(comparison) {
    const host = $("algorithmResults");
    host.replaceChildren();
    state.algorithmResults = comparison.results || [];
    $("visualizerPlay").dataset.cursor = "0";
    const visualizerButton = $("visualizerPlay");
    visualizerButton.disabled = !state.algorithmResults.some((result) => result.explored_edges?.length);
    $("visualizerMessage").textContent = visualizerButton.disabled
      ? (comparison.message || "Algorithm playback is unavailable until the compact road graph is loaded.")
      : "Choose an algorithm and press Play to inspect its sampled search.";
    resetVisualizer();
    $("comparisonMessage").textContent = comparison.message || "Algorithm comparison is unavailable for this route.";
    (comparison.results || []).forEach((result) => {
      const row = document.createElement("div");
      row.className = "algorithm-row";
      const name = document.createElement("strong");
      name.textContent = result.algorithm;
      const time = document.createElement("span");
      time.textContent = `${result.duration_min.toFixed(1)} min`;
      const distance = document.createElement("span");
      distance.textContent = `${result.distance_km.toFixed(1)} km`;
      row.append(name, time, distance);
      host.append(row);
    });
  }

  function renderDirections(instructions) {
    const list = $("directionsList");
    list.replaceChildren();
    $("stepCount").textContent = `${instructions.length} steps`;
    if (!instructions.length) {
      const empty = document.createElement("li");
      empty.className = "empty-directions";
      empty.textContent = "Step-by-step directions were not returned for this route.";
      list.append(empty);
      return;
    }
    instructions.forEach((item, index) => {
      const row = document.createElement("li");
      row.className = "direction-item";
      const number = document.createElement("span");
      number.className = "direction-number";
      number.textContent = String(index + 1);
      const text = document.createElement("span");
      text.className = "direction-text";
      text.textContent = item.instruction;
      const distance = document.createElement("span");
      distance.className = "direction-distance";
      distance.textContent = item.distance_km > 0 ? formatDistance(item.distance_km) : "";
      row.append(number, text, distance);
      list.append(row);
    });
  }

  function drawTrafficSections(route) {
    state.trafficSectionsLayer.clearLayers();
    if (!route?.traffic_segments?.length) return;
    const colors = { minor: "#f4b400", moderate: "#f28c28", heavy: "#e34b32", severe: "#c62828" };
    route.traffic_segments.forEach((segment) => {
      if (!Array.isArray(segment.coordinates) || segment.coordinates.length < 2) return;
      const severity = String(segment.severity || "unknown").toLowerCase();
      const line = L.polyline(segment.coordinates, {
        color: colors[severity] || "#e34b32",
        weight: 8,
        opacity: .96,
        lineCap: "round",
        lineJoin: "round",
      }).addTo(state.trafficSectionsLayer);
      const tooltip = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = `${severity === "unknown" ? "Traffic" : `${severity[0].toUpperCase()}${severity.slice(1)} traffic`}${segment.category ? ` · ${segment.category.replaceAll("_", " ").toLowerCase()}` : ""}`;
      tooltip.append(title);
      if (Number(segment.delay_min) > 0) {
        const delay = document.createElement("div");
        delay.textContent = `About +${Math.round(segment.delay_min)} min delay`;
        tooltip.append(delay);
      }
      if (segment.name) {
        const road = document.createElement("div");
        road.textContent = segment.name;
        tooltip.append(road);
      }
      line.bindTooltip(tooltip, { sticky: true });
    });
  }

  function selectActiveRoute(type) {
    const selected = type === "traffic" && state.trafficRoute ? state.trafficRoute : state.fastestRoute;
    if (!selected) return;
    state.activeRouteType = selected === state.trafficRoute ? "traffic" : "fastest";
    $("cardFastestRoute").classList.toggle("active", state.activeRouteType === "fastest");
    $("cardTrafficRoute").classList.toggle("active", state.activeRouteType === "traffic");

    if (state.fastestLayer) {
      state.fastestLayer.setStyle({ weight: state.activeRouteType === "fastest" ? 6 : 4, opacity: state.activeRouteType === "fastest" ? .96 : .55 });
    }
    if (state.trafficLayer) {
      state.trafficLayer.setStyle({ weight: state.activeRouteType === "traffic" ? 6 : 4, opacity: state.activeRouteType === "traffic" ? .96 : .55, dashArray: state.activeRouteType === "traffic" ? null : "7 7" });
    }
    (state.activeRouteType === "traffic" ? state.trafficLayer : state.fastestLayer)?.bringToFront();
    drawTrafficSections(selected);

    const live = selected.provider === "TomTom";
    $("summaryTitle").textContent = selected.label || (live ? "Fastest with live traffic" : "Road route estimate");
    $("summarySubtitle").textContent = live
      ? `TomTom live traffic · updated ${formatTrafficTime(state.liveTraffic?.updated_at)}`
      : "OSRM route estimate · live traffic unavailable";
    $("distanceValue").textContent = formatDistance(selected.distance_km);
    $("durationValue").textContent = formatDuration(selected.duration_min);
    const averageSpeed = selected.duration_min > 0 ? (selected.distance_km / selected.duration_min * 60).toFixed(1) : "—";
    $("averageSpeedValue").textContent = `${averageSpeed} km/h`;
    $("delayShareValue").textContent = selected.traffic_delay_min === null || selected.traffic_delay_min === undefined
      ? "Unavailable"
      : selected.traffic_delay_min > 0 ? `+${Math.round(selected.traffic_delay_min)} min` : "None detected";
    $("stopsValue").textContent = String(state.waypoints.length);
    renderDirections(selected.instructions || []);
    updateGoogleMapsLink();
    void loadMetroEstimate();
  }

  $("cardFastestRoute").addEventListener("click", () => selectActiveRoute("fastest"));
  $("cardTrafficRoute").addEventListener("click", () => selectActiveRoute("traffic"));

  function formatTrafficTime(value) {
    if (!value) return "just now";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "just now" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  function renderBothRoutes(data) {
    state.lastRouteData = data;
    state.liveTraffic = data.live_traffic || { available: false, configured: false, message: "Live traffic is unavailable." };
    const routes = Array.isArray(data.routes) && data.routes.length ? data.routes : [data.route || data.fastest_route].filter(Boolean);
    state.fastestRoute = routes[0] || null;
    state.trafficRoute = routes[1] || null;

    if (state.fastestLayer) map.removeLayer(state.fastestLayer);
    if (state.trafficLayer) map.removeLayer(state.trafficLayer);
    state.trafficSectionsLayer.clearLayers();
    state.rainMarkers.forEach((marker) => map.removeLayer(marker));
    state.rainMarkers = [];
    state.explorationLayers.clearLayers();

    $("cardTrafficRoute").hidden = !state.trafficRoute;
    $("dualRoutesContainer").classList.toggle("single-route", !state.trafficRoute);
    const isLive = state.liveTraffic.available === true;
    document.querySelector(".service-status").lastChild.textContent = isLive
      ? " Live traffic · TomTom"
      : " Road routes · live traffic unavailable";
    $("fastestRouteLabel").textContent = isLive ? "⚡ FASTEST WITH LIVE TRAFFIC" : "ROAD ROUTE ESTIMATE";
    $("trafficRouteLabel").textContent = isLive ? "LIVE TRAFFIC ALTERNATIVE" : "ALTERNATIVE ROAD ROUTE";
    $("fastestTimeSaved").textContent = isLive ? "Recommended" : "No live feed";
    $("fastestStatus").className = `route-card-status ${isLive ? "status-clear" : "status-neutral"}`;
    $("fastestStatus").lastChild.textContent = isLive ? " Live traffic · click to view" : " Live traffic unavailable · click to view";
    if (state.trafficRoute) {
      $("trafficDuration").textContent = formatDuration(state.trafficRoute.duration_min);
      $("trafficDistance").textContent = formatDistance(state.trafficRoute.distance_km);
      $("trafficDelayBadge").textContent = isLive && state.trafficRoute.traffic_delay_min > 0
        ? `+${Math.round(state.trafficRoute.traffic_delay_min)} min delay`
        : isLive ? "Live ETA" : "No live data";
      $("trafficStatus").className = `route-card-status ${isLive ? "status-congested" : "status-neutral"}`;
      $("trafficStatus").lastChild.textContent = isLive ? " Traffic-adjusted ETA · click to view" : " OSRM estimate · click to view";
    }
    if (state.fastestRoute) {
      $("fastestDuration").textContent = formatDuration(state.fastestRoute.duration_min);
      $("fastestDistance").textContent = formatDistance(state.fastestRoute.distance_km);
    }

    if (state.trafficRoute) {
      state.trafficLayer = L.polyline(state.trafficRoute.coordinates, {
        color: "#d97706", weight: 4, opacity: .68, dashArray: "7 7", lineCap: "round", lineJoin: "round",
      }).addTo(map).bindTooltip(state.liveTraffic.available ? "Live traffic-aware alternative" : "Alternative OSRM road route", { sticky: true });
    }
    if (state.fastestRoute) {
      state.fastestLayer = L.polyline(state.fastestRoute.coordinates, {
        color: "#059669", weight: 6, opacity: .96, lineCap: "round", lineJoin: "round",
      }).addTo(map).bindTooltip(state.liveTraffic.available ? "Fastest route with current traffic" : "OSRM road route estimate", { sticky: true });
    }
    (data.rain_risks || []).forEach((risk) => {
      const icon = L.divIcon({ className: "", html: '<div class="rain-marker" aria-hidden="true">🌧</div>', iconSize: [28, 28], iconAnchor: [14, 14] });
      const marker = L.marker([risk.lat, risk.lon], { icon }).addTo(map)
        .bindPopup(`<strong>Static rain-risk caution: ${risk.name}</strong><br><small>${risk.description}</small>`);
      state.rainMarkers.push(marker);
    });

    const combinedCoords = routes.flatMap((route) => route.coordinates || []);
    if (combinedCoords.length) map.fitBounds(L.latLngBounds(combinedCoords).pad(.18), { maxZoom: 15, animate: true });

    const banner = $("trafficBanner");
    banner.hidden = false;
    if (isLive) {
      const segmentCount = state.fastestRoute?.traffic_segments?.length || 0;
      const delay = Number(state.fastestRoute?.traffic_delay_min || 0);
      $("trafficBannerTitle").textContent = `Live traffic · updated ${formatTrafficTime(state.liveTraffic.updated_at)}`;
      $("trafficBannerText").textContent = segmentCount
        ? `${segmentCount} traffic-affected road section${segmentCount === 1 ? "" : "s"} shown on the map. Current route delay: ${Math.round(delay)} min.`
        : delay > 0
          ? `TomTom reports about ${Math.round(delay)} min of traffic delay, but did not map a specific affected section.`
          : "No traffic-affected sections were reported on this route at the time of the request.";
    } else {
      $("trafficBannerTitle").textContent = state.liveTraffic.configured ? "Live traffic temporarily unavailable" : "Live traffic needs a free API key";
      $("trafficBannerText").textContent = state.liveTraffic.message || "Showing an OSRM route estimate without live traffic adjustment.";
    }
    $("estimateDisclaimer").textContent = data.estimate_notice || state.liveTraffic.message;

    $("summaryStart").textContent = data.start.label;
    $("summaryDestination").textContent = data.destination.label;
    selectActiveRoute("fastest");
    renderAlgorithms(data.algorithm_comparison || {});
    $("results").hidden = false;
    updateGoogleMapsLink();
    if (state.avoidFlood) void showStaticRainHazards(true);
    void loadMetroEstimate();

    if (window.matchMedia("(max-width: 740px)").matches) {
      const panel = document.querySelector(".planner-panel");
      panel.dataset.sheetState = "peek";
      $("sheetHandle").setAttribute("aria-expanded", "false");
      setTimeout(() => map.invalidateSize({ animate: true }), 300);
      document.querySelector(".map-frame").scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      $("results").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  routeButton.addEventListener("click", async () => {
    if (!state.start || !state.destination) return;
    routeButton.disabled = true;
    routeButton.querySelector(".route-button-label").textContent = "Analyzing traffic & routes…";
    try {
      const result = await api("/api/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start: state.start,
          destination: state.destination,
          waypoints: state.waypoints,
          optimize_for: state.optimize,
        }),
      });
      hideNotice();
      renderBothRoutes(result);
    } catch (error) {
      showToast(error.message || "Road routing is temporarily unavailable. Please try again shortly.");
    } finally {
      routeButton.querySelector(".route-button-label").textContent = "Find best routes";
      routeButton.disabled = !(state.start && state.destination && allStopsReady());
    }
  });

  function updateGoogleMapsLink() {
    const link = $("googleMapsLink");
    if (!state.start || !state.destination) {
      link.href = "#";
      link.setAttribute("aria-disabled", "true");
      return;
    }
    const params = new URLSearchParams({
      api: "1",
      origin: `${state.start.lat},${state.start.lon}`,
      destination: `${state.destination.lat},${state.destination.lon}`,
      travelmode: "driving",
    });
    if (state.waypoints.length) {
      params.set("waypoints", state.waypoints.map((point) => `${point.lat},${point.lon}`).join("|"));
    }
    link.href = `https://www.google.com/maps/dir/?${params.toString()}`;
    link.removeAttribute("aria-disabled");
  }

  function shareableRouteUrl() {
    const url = new URL(window.location.href);
    url.search = "";
    if (state.start) url.searchParams.set("start", `${state.start.lat},${state.start.lon}`);
    if (state.destination) url.searchParams.set("dest", `${state.destination.lat},${state.destination.lon}`);
    state.waypoints.filter(Boolean).forEach((point) => url.searchParams.append("via", `${point.lat},${point.lon}`));
    if (state.avoidFlood) url.searchParams.set("rain", "1");
    return url.toString();
  }

  function parsePoint(value, label) {
    const parts = (value || "").split(",").map(Number);
    if (parts.length !== 2 || !Number.isFinite(parts[0]) || !Number.isFinite(parts[1])) return null;
    if (parts[0] < -90 || parts[0] > 90 || parts[1] < -180 || parts[1] > 180) return null;
    return { lat: parts[0], lon: parts[1], label };
  }

  async function loadMetroEstimate() {
    if (!state.start || !state.destination) return;
    const host = $("metroEstimate");
    host.textContent = "Calculating an illustrative metro estimate…";
    try {
      const result = await api("/api/transit/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start: state.start, destination: state.destination }),
      });
      if (!result.available) {
        host.textContent = result.message || "No metro estimate is available for this route.";
        return;
      }
      const roadMin = state.fastestRoute?.duration_min;
      const verdict = Number.isFinite(roadMin)
        ? result.estimated_duration_min < roadMin ? "Metro estimate is quicker" : "Road estimate is quicker"
        : "Illustrative metro estimate";
      host.replaceChildren();
      const total = document.createElement("div");
      total.className = "metro-main";
      total.textContent = `${result.estimated_duration_min} min`;
      const route = document.createElement("div");
      route.className = "metro-route";
      route.textContent = `${result.start_station} → ${result.destination_station} · ${result.walk_duration_min} min walk + ${result.train_duration_min} min train + wait`;
      const note = document.createElement("div");
      note.className = "metro-verdict";
      note.textContent = verdict;
      host.append(total, route, note);
    } catch (error) {
      host.textContent = error.message || "Metro estimate is temporarily unavailable.";
    }
  }

  async function showStaticRainHazards(enabled) {
    state.rainMarkers.forEach((marker) => map.removeLayer(marker));
    state.rainMarkers = [];
    if (!enabled) return;
    try {
      const result = await api("/api/rain/hazards");
      (result.hazards || []).forEach((risk) => {
        const icon = L.divIcon({ className: "", html: '<div class="rain-marker">🌧</div>', iconSize: [28, 28], iconAnchor: [14, 14] });
        const marker = L.marker([risk.lat, risk.lon], { icon })
          .addTo(map)
          .bindPopup(`<strong>Static caution area · ${risk.name}</strong><br><small>${risk.description}</small>`);
        state.rainMarkers.push(marker);
      });
    } catch {
      showNotice("Static monsoon caution locations could not be loaded.", "warning");
    }
  }

  function resetVisualizer() {
    if (state.explorationTimer) clearInterval(state.explorationTimer);
    state.explorationTimer = null;
    state.explorationLayers.clearLayers();
    $("exploredCount").textContent = "0";
    const button = $("visualizerPlay");
    if (button) button.textContent = "▶ Play";
  }

  function playVisualizer() {
    const result = state.algorithmResults.find((item) => item.algorithm === $("algorithmSelect").value);
    const edges = result?.explored_edges || [];
    if (!edges.length) {
      $("visualizerMessage").textContent = "No sampled search path is available for this algorithm.";
      return;
    }
    if (state.explorationTimer) {
      clearInterval(state.explorationTimer);
      state.explorationTimer = null;
      $("visualizerPlay").textContent = "▶ Resume";
      return;
    }
    let cursor = Number($("visualizerPlay").dataset.cursor || 0);
    if (cursor >= edges.length) { resetVisualizer(); cursor = 0; }
    $("visualizerPlay").textContent = "Ⅱ Pause";
    $("visualizerMessage").textContent = `Showing ${edges.length} sampled frontier edges from a search that explored ${result.nodes_explored.toLocaleString()} nodes.`;
    state.explorationTimer = setInterval(() => {
      const [from, to] = edges[cursor];
      L.polyline([from, to], { color: "#438cc8", weight: 2, opacity: .24, interactive: false })
        .addTo(state.explorationLayers);
      if (cursor % 5 === 0) {
        L.circleMarker(to, { radius: 3, color: "#fff", weight: 1, fillColor: "#438cc8", fillOpacity: .8, interactive: false })
          .addTo(state.explorationLayers);
      }
      cursor += 1;
      $("visualizerPlay").dataset.cursor = String(cursor);
      $("exploredCount").textContent = Math.min(
        result.nodes_explored,
        Math.round(result.nodes_explored * cursor / edges.length),
      ).toLocaleString();
      if (cursor >= edges.length) {
        clearInterval(state.explorationTimer);
        state.explorationTimer = null;
        $("visualizerPlay").textContent = "↻ Replay";
        $("exploredCount").textContent = Number(result.nodes_explored).toLocaleString();
      }
    }, 26);
  }

  $("myLocationButton").addEventListener("click", () => {
    if (!navigator.geolocation) {
      showToast("Location access is not available in this browser.");
      return;
    }
    $("myLocationButton").disabled = true;
    $("myLocationButton").textContent = "Locating you…";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        void chooseCoordinate(position.coords.latitude, position.coords.longitude, "start");
        $("myLocationButton").disabled = false;
        $("myLocationButton").textContent = "◎ Use my current location";
      },
      (error) => {
        showToast(error.code === error.PERMISSION_DENIED
          ? "Allow location access in your browser to use this feature."
          : "Your current location could not be found. Try again or pick a point on the map.");
        $("myLocationButton").disabled = false;
        $("myLocationButton").textContent = "◎ Use my current location";
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  });

  $("addStopButton").addEventListener("click", () => {
    if (state.waypoints.length >= 8) {
      showToast("You can add up to eight intermediate stops.");
      return;
    }
    const index = state.waypoints.push(null) - 1;
    renderWaypoints();
    setTarget(`stop-${index}`);
    showNotice(`Choose stop ${index + 1} on the map or search for a place.`);
  });

  $("optimizeStopsButton").addEventListener("click", async () => {
    if (!state.start || !state.destination || !allStopsReady()) return;
    const button = $("optimizeStopsButton");
    button.disabled = true;
    button.textContent = "Optimizing…";
    try {
      const points = [state.start, ...state.waypoints, state.destination];
      const result = await api("/api/route/optimize-order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ points }),
      });
      state.start = result.points[0];
      state.destination = result.points[result.points.length - 1];
      state.waypoints = result.points.slice(1, -1);
      Object.values(state.markers).forEach((marker) => map.removeLayer(marker));
      state.markers = {};
      if (state.start) markerFor("start", state.start);
      state.waypoints.forEach((point, index) => markerFor(`stop-${index}`, point));
      if (state.destination) markerFor("destination", state.destination);
      updatePlanner();
      showNotice(`Stop order optimized. Estimated driving time: ${Math.round(result.estimated_drive_min)} min.`);
    } catch (error) {
      showToast(error.message || "Stop order optimization is temporarily unavailable.");
    } finally {
      button.textContent = "↻ Optimize stop order";
      renderWaypoints();
    }
  });

  $("avoidFloodToggle").addEventListener("change", (event) => {
    state.avoidFlood = event.target.checked;
    void showStaticRainHazards(state.avoidFlood);
    if (state.lastRouteData) showNotice("Find routes again to apply monsoon caution mode.");
  });

  $("shareRouteButton").addEventListener("click", async () => {
    if (!state.start || !state.destination) {
      showToast("Choose a start and destination before sharing.");
      return;
    }
    const url = shareableRouteUrl();
    try {
      await navigator.clipboard.writeText(url);
      showToast("Shareable route link copied.");
    } catch {
      showToast(url);
    }
  });

  $("visualizerPlay").addEventListener("click", playVisualizer);
  $("visualizerReset").addEventListener("click", () => {
    $("visualizerPlay").dataset.cursor = "0";
    resetVisualizer();
  });
  $("algorithmSelect").addEventListener("change", () => {
    $("visualizerPlay").dataset.cursor = "0";
    resetVisualizer();
  });

  let suppressHandleClick = false;
  $("sheetHandle").addEventListener("click", () => {
    if (suppressHandleClick) { suppressHandleClick = false; return; }
    const panel = document.querySelector(".planner-panel");
    const isPeek = panel.dataset.sheetState === "peek";
    panel.dataset.sheetState = isPeek ? "expanded" : "peek";
    $("sheetHandle").setAttribute("aria-expanded", String(isPeek));
    $("sheetHandle").setAttribute("aria-label", isPeek ? "Collapse route planner" : "Expand route planner");
    setTimeout(() => map.invalidateSize({ animate: true }), 300);
  });
  (() => {
    const panel = document.querySelector(".planner-panel");
    const handle = $("sheetHandle");
    if (window.matchMedia("(max-width: 740px)").matches) panel.dataset.sheetState = "expanded";
    let startY = null;
    handle.addEventListener("pointerdown", (event) => { startY = event.clientY; handle.setPointerCapture(event.pointerId); });
    handle.addEventListener("pointerup", (event) => {
      if (startY === null) return;
      const delta = event.clientY - startY;
      startY = null;
      if (Math.abs(delta) < 28) return;
      suppressHandleClick = true;
      setTimeout(() => { suppressHandleClick = false; }, 400);
      const expanded = delta < 0;
      panel.dataset.sheetState = expanded ? "expanded" : "peek";
      handle.setAttribute("aria-expanded", String(expanded));
      setTimeout(() => map.invalidateSize({ animate: true }), 300);
    });
  })();

  (() => {
    const params = new URLSearchParams(window.location.search);
    const start = parsePoint(params.get("start"), "Shared start");
    const destination = parsePoint(params.get("dest"), "Shared destination");
    if (!start || !destination) return;
    state.avoidFlood = params.get("rain") === "1";
    $("avoidFloodToggle").checked = state.avoidFlood;
    if (state.avoidFlood) void showStaticRainHazards(true);
    state.waypoints = params.getAll("via").slice(0, 8).map((value, index) => parsePoint(value, `Shared stop ${index + 1}`)).filter(Boolean);
    addPoint("start", start);
    state.waypoints.forEach((point, index) => { markerFor(`stop-${index}`, point); });
    addPoint("destination", destination);
    map.fitBounds(L.latLngBounds([start, ...state.waypoints, destination].map((point) => [point.lat, point.lon])).pad(.2));
    setTimeout(() => { if (!routeButton.disabled) routeButton.click(); }, 250);
  })();

  updatePlanner();
  setTarget("start");
  api("/api/traffic/status").then((status) => {
    document.querySelector(".service-status").lastChild.textContent = status.available
      ? " TomTom traffic ready · automatic"
      : " Road routes · live traffic key needed";
  }).catch(() => {
    document.querySelector(".service-status").lastChild.textContent = " Road routes · traffic status unavailable";
  });
})();
