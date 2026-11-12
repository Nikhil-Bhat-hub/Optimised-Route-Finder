(() => {
  const BENGALURU = [12.9716, 77.5946];
  const state = {
    start: null,
    destination: null,
    target: "start",
    optimize: "time",
    traffic: "normal",
    activeRouteType: "fastest",
    fastestRoute: null,
    trafficRoute: null,
    markers: {},
    fastestLayer: null,
    trafficLayer: null,
    hotspotMarkers: [],
    toastTimer: null,
    searchSequence: 0,
  };

  const $ = (id) => document.getElementById(id);
  const map = L.map("map", { zoomControl: false, scrollWheelZoom: true }).setView(BENGALURU, 12);
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
    chip.innerHTML = `<i class="mini-dot ${target === "start" ? "a-dot" : "b-dot"}"></i> ${target === "start" ? "Start point" : "Destination"}`;
  }

  function updatePlanner() {
    [["start", "startValue"], ["destination", "destinationValue"]].forEach(([key, id]) => {
      const value = $(id);
      value.textContent = state[key]?.label || "Choose a point";
      value.classList.toggle("is-set", Boolean(state[key]));
      document.querySelector(`[data-clear="${key}"]`).hidden = !state[key];
    });
    const ready = Boolean(state.start && state.destination);
    routeButton.disabled = !ready;
    document.querySelector(".button-hint").textContent = ready ? "Ready to find optimal & traffic routes" : "Select a start and destination to continue";
  }

  function markerFor(target, point) {
    const css = target === "start" ? "start" : "destination";
    const label = target === "start" ? "A" : "B";
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
    state[target] = { lat: Number(point.lat), lon: Number(point.lon), label: point.label || "Selected point" };
    markerFor(target, state[target]);
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
      showNotice(`${target === "start" ? "Start" : "Destination"} set to ${result.label}.`, "info");
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
        showNotice(`${state.target === "start" ? "Start" : "Destination"} set to ${result.label}.`, "info");
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
    renderDirections(selected.instructions || []);
  }

  $("cardFastestRoute").addEventListener("click", () => selectActiveRoute("fastest"));
  $("cardTrafficRoute").addEventListener("click", () => selectActiveRoute("traffic"));

  function renderBothRoutes(data) {
    state.fastestRoute = data.fastest_route || data.route;
    state.trafficRoute = data.traffic_route || data.route;
    const hotspots = data.traffic_hotspots || [];

    // Clear previous polylines & markers
    if (state.fastestLayer) map.removeLayer(state.fastestLayer);
    if (state.trafficLayer) map.removeLayer(state.trafficLayer);
    state.hotspotMarkers.forEach((m) => map.removeLayer(m));
    state.hotspotMarkers = [];

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
      bannerTitle.textContent = "⚡ Dynamic Traffic Rerouting Active";
      bannerText.textContent = data.reroute_reason;
    } else if (state.trafficRoute.traffic_delay_min > 0) {
      banner.hidden = false;
      bannerTitle.textContent = "⚠️ Traffic Congestion Monitored";
      bannerText.textContent = `Moderate congestion detected on primary route (+${state.trafficRoute.traffic_delay_min.toFixed(0)} min delay).`;
    } else {
      banner.hidden = false;
      bannerTitle.textContent = "✓ Clear Traffic Flow";
      bannerText.textContent = "Traffic is flowing smoothly. Both routes are experiencing minimal delays.";
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
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
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
          optimize_for: state.optimize,
          traffic_mode: state.traffic,
        }),
      });
      hideNotice();
      renderBothRoutes(result);
    } catch (error) {
      showToast(error.message || "Live routing is temporarily unavailable. Please try again shortly.");
    } finally {
      routeButton.querySelector(".route-button-label").textContent = "Find best routes";
      routeButton.disabled = !(state.start && state.destination);
    }
  });

  updatePlanner();
  setTarget("start");
  fetch("/health").then((response) => response.ok ? response.json() : null).then((health) => {
    if (health) {
      document.querySelector(".service-status").lastChild.textContent = " Live road routing & traffic";
    }
  }).catch(() => {});
})();
