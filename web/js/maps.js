/* Three maps, two panels: the target map shows the Moon (south polar) or Mars, the Earth map shows candidates.
 * The target map is rebuilt when the mission changes because the Moon and Mars use different projections. */
(function (ET, L) {
  "use strict";

  var M = ET.Maps = {};
  var target = null, targetBody = null, siteLayer = null, siteMarkers = {};
  var earth = null, candLayer = null, candMarkers = {};
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function crsFor(name) {
    if (name === "moon-sp") return ET.CRS_MOON_SP;
    if (name === "eq") return L.CRS.EPSG4326;
    return L.CRS.EPSG3857;
  }

  function stateBadge(el, mode, def) {
    var text, cls = "badge";
    if (mode === "live") text = "Live · " + def.name.split("·").pop().trim();
    else if (mode === "unverified") text = "Live (unverified) · " + def.name.split("·").pop().trim();
    else if (mode === "fallback") { text = "Static fallback image"; cls += " fallback"; }
    else text = "Checking tiles…";
    el.innerHTML = '<span class="' + cls + '" data-tip="' + ET.esc(def.name + (mode === "fallback" ? " did not return usable tiles; showing a bundled static copy." : "")) + '">' + ET.esc(text) + "</span>";
  }

  function buildMap(elId, cfg, stateEl) {
    var map = L.map(elId, {
      crs: crsFor(cfg.crs), center: cfg.view.center, zoom: cfg.view.zoom, minZoom: cfg.view.minZoom, maxZoom: cfg.view.maxZoom,
      zoomControl: true, attributionControl: true, worldCopyJump: false, zoomSnap: 0.5,
      fadeAnimation: !reduceMotion, zoomAnimation: !reduceMotion
    });
    map.attributionControl.setPrefix(false);
    var first = cfg.base[0];
    stateBadge(stateEl, "checking", first);
    var guarded = ET.guardLayer(map, first, cfg.fallback, function (mode) { stateBadge(stateEl, mode, first); });
    guarded.layer.addTo(map);
    var bases = {}; bases[first.name] = guarded.layer;
    cfg.base.slice(1).forEach(function (d) { bases[d.name] = ET.makeLayer(d); });
    var overlays = {};
    cfg.overlays.forEach(function (d) { overlays[d.name] = ET.makeLayer(d); });
    L.control.layers(bases, overlays, { collapsed: true, position: "topright" }).addTo(map);
    ET.probeAll(cfg.base.slice(1).concat(cfg.overlays));
    watchSize(map);
    return map;
  }

  /** Re-measure the map whenever its box changes size (window resize, layout switch, hidden → shown, page zoom).
   * Without this Leaflet keeps an old size and only fills part of the box with tiles. */
  function watchSize(map) {
    if (!("ResizeObserver" in window)) return;
    var el = map.getContainer(), raf = 0;
    var ro = new ResizeObserver(function () {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(function () { if (el.clientWidth && el.clientHeight) map.invalidateSize({ pan: false }); });
    });
    ro.observe(el);
    map.on("unload", function () { ro.disconnect(); cancelAnimationFrame(raf); });
  }

  /* ---------------------------------------------------------- target */
  function moonGraticule(map) {
    var g = L.layerGroup().addTo(map);
    var style = { color: "#fff", weight: 0.6, opacity: 0.28, dashArray: "2 4", interactive: false };
    [-80, -85, -88].forEach(function (lat) {
      var pts = [];
      for (var lng = -180; lng <= 180; lng += 3) pts.push([lat, lng]);
      L.polyline(pts, style).addTo(g);
      L.marker([lat, 0], { interactive: false, icon: L.divIcon({ className: "grat-label", html: Math.abs(lat) + "°S", iconSize: null }) }).addTo(g);
    });
    for (var lng = -180; lng < 180; lng += 30) L.polyline([[-76, lng], [-89.7, lng]], style).addTo(g);
    [[0, "0°"], [90, "90°E"], [180, "180°"], [-90, "90°W"]].forEach(function (m) {
      L.marker([-76.2, m[0]], { interactive: false, icon: L.divIcon({ className: "grat-label", html: m[1], iconSize: null }) }).addTo(g);
    });
  }

  function marsBand(map) {
    var pts = [];
    for (var lng = -180; lng <= 180; lng += 5) pts.push([30, lng]);
    for (lng = 180; lng >= -180; lng -= 5) pts.push([45, lng]);
    L.polygon(pts, { color: "#5cc8ff", weight: 1, opacity: 0.7, dashArray: "4 4", fillColor: "#5cc8ff", fillOpacity: 0.06, interactive: false }).addTo(map);
    L.marker([45.5, -110], { interactive: false, icon: L.divIcon({ className: "grat-label", html: "SKYFALL STUDY BAND · 30–45°N", iconSize: null }) }).addTo(map);
  }

  M.setMission = function (mission, sites, onSiteClick) {
    var body = mission.body;
    if (target && targetBody === body) return M.drawSites(sites, onSiteClick);
    if (target) { target.remove(); target = null; }
    targetBody = body;
    var cfg = ET.LAYERS[body];
    target = buildMap("map-target", cfg, document.getElementById("target-layerstate"));
    if (body === "moon") moonGraticule(target); else marsBand(target);
    M.drawSites(sites, onSiteClick);
  };

  M.drawSites = function (sites, onSiteClick) {
    if (siteLayer) siteLayer.remove();
    siteLayer = L.layerGroup().addTo(target);
    siteMarkers = {};
    sites.forEach(function (s) {
      var p = s.position || {};
      if (p.lat === null || p.lat === undefined) return;   // no coordinates in the team documents: not drawn
      var m = L.marker([p.lat, p.lon], {
        icon: L.divIcon({ className: "", html: '<div class="site-pin"></div>', iconSize: [14, 14], iconAnchor: [7, 7] }),
        keyboard: true, title: s.name
      }).addTo(siteLayer);
      m.bindTooltip(ET.esc(s.name) + (p.note ? '<br><span style="color:#8b929c">' + ET.esc(p.note) + "</span>" : ""), { direction: "right", offset: [10, 0], permanent: false });
      m.on("click", function () { onSiteClick(s.id); });
      siteMarkers[s.id] = m;
    });
  };

  M.selectSite = function (site) {
    Object.keys(siteMarkers).forEach(function (id) {
      var el = siteMarkers[id].getElement();
      if (el) el.firstChild.classList.toggle("sel", id === site.id);
    });
    var p = site.position || {};
    if (p.lat !== null && p.lat !== undefined && target) {
      var z = Math.max(target.getZoom(), targetBody === "moon" ? 3 : 4);
      if (reduceMotion) target.setView([p.lat, p.lon], z); else target.flyTo([p.lat, p.lon], z, { duration: 0.8 });
    }
  };

  /* ---------------------------------------------------------- earth */
  M.initEarth = function () {
    earth = buildMap("map-earth", ET.LAYERS.earth, document.getElementById("earth-layerstate"));
    L.control.scale({ imperial: false, position: "bottomleft" }).addTo(earth);
  };

  M.drawCandidates = function (entries, byId, handlers) {
    if (candLayer) candLayer.remove();
    candLayer = L.layerGroup().addTo(earth);
    candMarkers = {};
    entries.forEach(function (e) {
      var c = byId[e.id];
      var m;
      if (e.group === "analog") {
        m = L.marker([c.lat, c.lon], {
          icon: L.divIcon({ className: "", html: '<div class="pin" data-id="' + ET.esc(e.id) + '">' + e.rank + "</div>", iconSize: [26, 26], iconAnchor: [13, 13] }),
          zIndexOffset: 1000 - e.rank, title: c.name, keyboard: true
        });
      } else {
        var style = {
          low_match: { radius: 5, color: "#8b929c", weight: 1, fillColor: "#8b929c", fillOpacity: 0.35 },
          rejected: { radius: 4, color: "#fff", weight: 1, fillOpacity: 0, dashArray: null },
          cannot_evaluate: { radius: 4, color: "#5a616b", weight: 1, fillOpacity: 0, dashArray: "2 2" }
        }[e.group];
        m = L.circleMarker([c.lat, c.lon], style);
      }
      var label = { analog: "Analog #" + e.rank + " · " + e.score_pct + "%", low_match: "Low match · " + e.score_pct + "%", rejected: "Rejected", cannot_evaluate: "Cannot be evaluated" }[e.group];
      m.bindTooltip("<b>" + ET.esc(c.name) + "</b><br>" + ET.esc(label), { direction: "top", offset: [0, -10] });
      m.on("click", function () { handlers.select(e.id); });
      m.on("mouseover", function () { handlers.hover(e.id, true); });
      m.on("mouseout", function () { handlers.hover(e.id, false); });
      m.addTo(candLayer);
      candMarkers[e.id] = m;
    });
  };

  M.selectCandidate = function (id, cand) {
    Object.keys(candMarkers).forEach(function (k) {
      var el = candMarkers[k].getElement && candMarkers[k].getElement();
      var pin = el && el.querySelector && el.querySelector(".pin");
      if (pin) pin.classList.toggle("sel", k === id);
    });
    if (cand && earth) {
      var z = Math.max(earth.getZoom(), 5);
      if (reduceMotion) earth.setView([cand.lat, cand.lon], z); else earth.flyTo([cand.lat, cand.lon], z, { duration: 0.9 });
    }
  };

  M.hoverCandidate = function (id, on) {
    var m = candMarkers[id];
    var el = m && m.getElement && m.getElement();
    var pin = el && el.querySelector && el.querySelector(".pin");
    if (pin) pin.classList.toggle("hot", on);
    else if (m && m.setStyle) m.setStyle({ weight: on ? 3 : 1 });
    if (m && on) m.openTooltip(); else if (m) m.closeTooltip();
  };

  M.overview = function () {
    if (earth) earth.setView(ET.LAYERS.earth.view.center, ET.LAYERS.earth.view.zoom);
  };

  M.invalidate = function () {
    setTimeout(function () { if (target) target.invalidateSize(); if (earth) earth.invalidateSize(); }, 50);
  };
})(window.ET, window.L);
