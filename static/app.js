(() => {
  const BENGALURU = [12.9716, 77.5946];
  const state = {
    start: null,
    destination: null,
    waypoints: [],
    target: "start",
    optimize: "time",
    traffic: "normal",
    avoidFlood: false,
    activeRouteType: "fastest",
    fastestRoute: null,
    trafficRoute: null,
    markers: {},
    fastestLayer: null,
    trafficLayer: null,
    hotspotMarkers: [],
    rainMarkers: [],
    searchLayers: L.layerGroup(),
    algorithmResults: [],
    explorationLayers: L.layerGroup(),
    explorationTimer: null,
    elevationChart: null,
    lastRouteData: null,
    toastTimer: null,
    searchSequence: 0,
  };

  const $ = (id) => document.getElementById(id);
  const map = L.map("map", { zoomControl: false, scrollWheelZoom: true }).setView(BENGALURU, 12);
  state.searchLayers.addTo(map);
  state.explorationLayers.addTo(map);
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

  document.querySelectorAll("[data-traffic]").forEach((button) => button.addEventListener("click", () => {
    state.traffic = button.dataset.traffic;
    document.querySelectorAll("[data-traffic]").forEach((item) => {
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

  function selectActiveRoute(type) {
    state.activeRouteType = type;
    const isFastest = type === "fastest";
    const selected = isFastest ? state.fastestRoute : state.trafficRoute;
    if (!selected) return;

    // Update card styling
    $("cardFastestRoute").classList.toggle("active", isFastest);
    $("cardTrafficRoute").classList.toggle("active", !isFastest);

    // Update layers emphasis
    if (state.fastestLayer && state.trafficLayer) {
      if (isFastest) {
        state.fastestLayer.setStyle({ weight: 6, opacity: 0.95, dashArray: null });
        state.trafficLayer.setStyle({ weight: 4, opacity: 0.65, dashArray: "6, 6" });
        state.fastestLayer.bringToFront();
      } else {
        state.trafficLayer.setStyle({ weight: 6, opacity: 0.95, dashArray: null });
        state.fastestLayer.setStyle({ weight: 4, opacity: 0.65, dashArray: "6, 6" });
        state.trafficLayer.bringToFront();
      }
    }

    // Update summary metrics
    $("summaryTitle").textContent = selected.label || (isFastest ? "Fastest Route" : "Route with Traffic");
    $("summarySubtitle").textContent = isFastest
      ? "Optimal traffic-avoidance path · OSRM"
      : "Standard corridor · includes bottleneck delays";
    $("distanceValue").textContent = formatDistance(selected.distance_km);
    $("durationValue").textContent = formatDuration(selected.duration_min);
    const averageSpeed = selected.duration_min > 0
      ? (selected.distance_km / selected.duration_min * 60).toFixed(1)
      : "—";
    const delayShare = selected.duration_min > 0
      ? `${Math.round((selected.traffic_delay_min || 0) / selected.duration_min * 100)}%`
      : "—";
    $("averageSpeedValue").textContent = `${averageSpeed} km/h`;
    $("delayShareValue").textContent = delayShare;
    $("stopsValue").textContent = String(state.waypoints.length);
    renderDirections(selected.instructions || []);
    updateGoogleMapsLink();
    void loadElevation(selected);
    void loadMetroEstimate();
  }

  $("cardFastestRoute").addEventListener("click", () => selectActiveRoute("fastest"));
  $("cardTrafficRoute").addEventListener("click", () => selectActiveRoute("traffic"));

  function renderBothRoutes(data) {
    state.lastRouteData = data;
    state.fastestRoute = data.fastest_route || data.route;
    state.trafficRoute = data.traffic_route || data.route;
    const hotspots = data.traffic_hotspots || [];

    // Clear previous polylines & markers
    if (state.fastestLayer) map.removeLayer(state.fastestLayer);
    if (state.trafficLayer) map.removeLayer(state.trafficLayer);
    state.hotspotMarkers.forEach((m) => map.removeLayer(m));
    state.hotspotMarkers = [];
    state.rainMarkers.forEach((m) => map.removeLayer(m));
    state.rainMarkers = [];
    state.explorationLayers.clearLayers();

    // 1. Draw Traffic Route polyline (Red/Amber)
    state.trafficLayer = L.polyline(state.trafficRoute.coordinates, {
      color: "#dc2626",
      weight: 4,
      opacity: 0.65,
      dashArray: "6, 6",
      lineCap: "round",
      lineJoin: "round",
    }).addTo(map).bindTooltip("⚠️ Route with Traffic", { sticky: true });

    // 2. Draw Fastest Route polyline (Emerald Green)
    state.fastestLayer = L.polyline(state.fastestRoute.coordinates, {
      color: "#059669",
      weight: 6,
      opacity: 0.95,
      lineCap: "round",
      lineJoin: "round",
    }).addTo(map).bindTooltip("⚡ Fastest Route (Traffic Avoided)", { sticky: true });

    // 3. Add bottleneck hazard markers
    hotspots.forEach((spot) => {
      const hazardIcon = L.divIcon({
        className: "",
        html: `<div class="traffic-marker" title="${spot.name}"><span>⚠️</span></div>`,
        iconSize: [26, 26],
        iconAnchor: [13, 13],
      });
      const marker = L.marker([spot.lat, spot.lon], { icon: hazardIcon })
        .addTo(map)
        .bindPopup(`<strong>⚠️ ${spot.name}</strong><br><small>${spot.description}</small><br><strong>Severity:</strong> ${spot.severity.toUpperCase()}<br><strong>Est. Delay:</strong> ~${spot.delay_min || 0} min`);
      state.hotspotMarkers.push(marker);
    });
    (data.rain_risks || []).forEach((risk) => {
      const rainIcon = L.divIcon({
        className: "",
        html: '<div class="rain-marker" aria-hidden="true">🌧</div>',
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      });
      const marker = L.marker([risk.lat, risk.lon], { icon: rainIcon })
        .addTo(map)
        .bindPopup(`<strong>Static rain-risk caution: ${risk.name}</strong><br><small>${risk.description}</small>`);
      state.rainMarkers.push(marker);
    });

    // Fit bounds to show both routes
    const combinedCoords = [...state.fastestRoute.coordinates, ...state.trafficRoute.coordinates];
    if (combinedCoords.length) {
      map.fitBounds(L.latLngBounds(combinedCoords).pad(0.18), { maxZoom: 15, animate: true });
    }

    // 4. Update Traffic Alert Banner
    const banner = $("trafficBanner");
    const bannerTitle = $("trafficBannerTitle");
    const bannerText = $("trafficBannerText");
    if (data.has_traffic_reroute) {
      banner.hidden = false;
      bannerTitle.textContent = "⚡ Recommended alternative found";
      bannerText.textContent = data.reroute_reason;
    } else if (state.trafficRoute.traffic_delay_min > 0) {
      banner.hidden = false;
      bannerTitle.textContent = "⚠️ Modeled congestion on this corridor";
      bannerText.textContent = `The hotspot model estimates about +${state.trafficRoute.traffic_delay_min.toFixed(0)} min on the selected corridor.`;
    } else {
      banner.hidden = false;
      bannerTitle.textContent = "✓ Route estimate ready";
      bannerText.textContent = "No significant delay was found by the configured hotspot model.";
    }

    // 5. Update Dual Route Cards
    $("fastestDuration").textContent = formatDuration(state.fastestRoute.duration_min);
    $("fastestDistance").textContent = formatDistance(state.fastestRoute.distance_km);
    $("fastestTimeSaved").textContent = data.has_traffic_reroute
      ? `Saves ${Math.round(data.time_saved_min)} min`
      : "Optimal route";

    $("trafficDuration").textContent = formatDuration(state.trafficRoute.duration_min);
    $("trafficDistance").textContent = formatDistance(state.trafficRoute.distance_km);
    $("trafficDelayBadge").textContent = state.trafficRoute.traffic_delay_min > 0
      ? `+${Math.round(state.trafficRoute.traffic_delay_min)} min delay`
      : "Standard path";

    $("cardTrafficRoute").classList.toggle("is-congested", state.trafficRoute.traffic_delay_min > 0);

    $("summaryStart").textContent = data.start.label;
    $("summaryDestination").textContent = data.destination.label;

    selectActiveRoute("fastest");
    renderAlgorithms(data.algorithm_comparison || {});

    $("results").hidden = false;
    updateGoogleMapsLink();
    void loadElevation(state.fastestRoute);
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
          traffic_mode: state.traffic,
          avoid_flood: state.avoidFlood,
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
    url.searchParams.set("traffic", state.traffic);
    if (state.avoidFlood) url.searchParams.set("rain", "1");
    return url.toString();
  }

  function parsePoint(value, label) {
    const parts = (value || "").split(",").map(Number);
    if (parts.length !== 2 || !Number.isFinite(parts[0]) || !Number.isFinite(parts[1])) return null;
    if (parts[0] < -90 || parts[0] > 90 || parts[1] < -180 || parts[1] > 180) return null;
    return { lat: parts[0], lon: parts[1], label };
  }

  async function loadElevation(route) {
    const canvas = $("elevationChart");
    if (!route?.coordinates?.length || !window.Chart) {
      $("elevationNotice").textContent = "Elevation chart is unavailable right now.";
      return;
    }
    const coords = route.coordinates;
    const sampleCount = Math.min(28, coords.length);
    const sampled = Array.from({ length: sampleCount }, (_, index) => coords[
      Math.round(index * (coords.length - 1) / Math.max(1, sampleCount - 1))
    ]);
    $("elevationNotice").textContent = "Loading approximate terrain elevations…";
    try {
      const result = await api("/api/elevation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          coordinates: sampled.map(([lat, lon], index) => ({ lat, lon, label: `Point ${index + 1}` })),
        }),
      });
      const profile = result.profile || [];
      if (state.elevationChart) state.elevationChart.destroy();
      state.elevationChart = new Chart(canvas, {
        type: "line",
        data: {
          labels: profile.map((point) => `${point.distance_km.toFixed(1)} km`),
          datasets: [{
            data: profile.map((point) => point.elevation_m),
            borderColor: "#178879",
            backgroundColor: "rgba(23,136,121,.12)",
            fill: true,
            tension: .35,
            pointRadius: 0,
            borderWidth: 2,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { displayColors: false } },
          scales: {
            x: { grid: { display: false }, ticks: { maxTicksLimit: 5, color: "#87948e", font: { size: 9 } } },
            y: { grid: { color: "#edf1ee" }, ticks: { maxTicksLimit: 4, color: "#87948e", font: { size: 9 } } },
          },
        },
      });
      $("elevationNotice").textContent = result.estimate_notice;
    } catch (error) {
      $("elevationNotice").textContent = error.message || "Terrain profile is temporarily unavailable.";
    }
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
        body: JSON.stringify({ points, traffic_mode: state.traffic }),
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
    state.traffic = ["normal", "peak", "offpeak"].includes(params.get("traffic")) ? params.get("traffic") : "normal";
    state.avoidFlood = params.get("rain") === "1";
    $("avoidFloodToggle").checked = state.avoidFlood;
    if (state.avoidFlood) void showStaticRainHazards(true);
    document.querySelectorAll("[data-traffic]").forEach((button) => {
      const active = button.dataset.traffic === state.traffic;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    state.waypoints = params.getAll("via").slice(0, 8).map((value, index) => parsePoint(value, `Shared stop ${index + 1}`)).filter(Boolean);
    addPoint("start", start);
    state.waypoints.forEach((point, index) => { markerFor(`stop-${index}`, point); });
    addPoint("destination", destination);
    map.fitBounds(L.latLngBounds([start, ...state.waypoints, destination].map((point) => [point.lat, point.lon])).pad(.2));
    setTimeout(() => { if (!routeButton.disabled) routeButton.click(); }, 250);
  })();

  updatePlanner();
  setTarget("start");
  fetch("/health").then((response) => response.ok ? response.json() : null).then((health) => {
    if (health) {
      document.querySelector(".service-status").lastChild.textContent = " Road routes · modeled traffic";
    }
  }).catch(() => {});
})();
