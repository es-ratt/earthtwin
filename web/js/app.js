/* App wiring: load data, hash routing between the views, keep state in the URL, render, handle clicks.
 *
 * Routes (hash):  #home  #moon-analog  #mars-analog  #why-not-others  #method  #limitations  #sources  #planex
 * Extra state after the route, e.g. #moon-analog&s=haworth&c=mcmurdo-dry-valleys  or  #method&m=skyfall&s=ap-105
 * Old links (#m=…&s=…&t=…) are still understood. */
(function (ET) {
  "use strict";

  var ROUTES = {
    "home": { view: "home" },
    "moon-analog": { view: "analogs", body: "moon" },
    "mars-analog": { view: "analogs", body: "mars" },
    "why-not-others": { view: "why" },
    "method": { view: "method" },
    "limitations": { view: "limits" },
    "sources": { view: "sources" },
    "planex": { view: "planex" }
  };
  var LEGACY_TABS = { why: "why-not-others", method: "method", limits: "limitations", sources: "sources" };
  var WORLD_KEY = "earthtwin.world";        // last chosen world (moon | mars), kept while the user navigates

  /* ------------------------------------------------------------ world memory (sessionStorage; optional) */
  function rememberWorld(body) { try { sessionStorage.setItem(WORLD_KEY, body); } catch (e) { /* storage blocked: fine */ } }
  function storedWorld() { try { return sessionStorage.getItem(WORLD_KEY); } catch (e) { return null; } }

  var data = {};
  var state = { route: "home", missionId: null, siteId: null, candidateId: null, whyFilter: "all", sourceQuery: "" };
  var maps = { ready: false, missionId: null, siteId: null };

  /* ------------------------------------------------------------ url state */
  function parseHash() {
    var h = { route: null };
    location.hash.replace(/^#\/?/, "").split("&").forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf("=");
      if (i < 0) { if (!h.route) h.route = decodeURIComponent(kv); return; }
      h[kv.slice(0, i)] = decodeURIComponent(kv.slice(i + 1));
    });
    if (!h.route && h.t) h.route = h.t === "analogs" ? (h.m === "skyfall" ? "mars-analog" : "moon-analog") : LEGACY_TABS[h.t];
    if (!ROUTES[h.route]) h.route = "home";
    return h;
  }

  function buildHash() {
    var parts = [state.route];
    if (state.route === "home" || state.route === "planex") return "#" + state.route;
    if (ROUTES[state.route].view !== "analogs") parts.push("m=" + state.missionId);
    parts.push("s=" + state.siteId);
    if (state.candidateId && ROUTES[state.route].view === "analogs") parts.push("c=" + state.candidateId);
    return "#" + parts.join("&");
  }

  function writeHash() { if (location.hash !== buildHash()) history.replaceState(null, "", buildHash()); }

  /** Change view: pushes a history entry so the Back button works. */
  function go(route, extra) {
    state.route = route;
    if (extra && extra.missionId) setMission(extra.missionId, extra.siteId);
    if (extra && "candidateId" in extra) state.candidateId = extra.candidateId;
    var target = buildHash();
    if (location.hash === target) show(); else location.hash = target;
  }

  /* ------------------------------------------------------------ state helpers */
  function mission() { return data.missionsById[state.missionId]; }
  function siteRes() { return data.results[state.missionId].sites[state.siteId]; }
  function missionForBody(body) { return data.missions.find(function (m) { return m.in_selector && m.body === body; }); }
  function routeForMission(m) { return m.body === "mars" ? "mars-analog" : "moon-analog"; }
  function siteIdsOf(m) { return m.target_site_ids.concat(m.reference_site_ids || []); }

  function setMission(missionId, siteId) {
    var changed = missionId !== state.missionId;
    state.missionId = missionId;
    var m = mission();
    rememberWorld(m.body);
    if (siteId && siteIdsOf(m).indexOf(siteId) >= 0) state.siteId = siteId;
    else if (changed || !state.siteId) state.siteId = m.default_site_id;
    if (changed) state.candidateId = null;
  }

  function setCandidate(id) {
    state.candidateId = id && siteRes().candidates.some(function (e) { return e.id === id; }) ? id : null;
  }

  /* ------------------------------------------------------------ maps (created only when the Analog view is visible) */
  function syncMaps(flyToCandidate) {
    if (!maps.ready) { ET.Maps.initEarth(); maps.ready = true; }
    var m = mission();
    if (maps.missionId !== state.missionId) {
      ET.Maps.setMission(m, siteIdsOf(m).map(function (id) { return data.sitesById[id]; }), selectSite);
      maps.missionId = state.missionId; maps.siteId = null;
    }
    if (maps.siteId !== state.siteId) {
      ET.Maps.selectSite(data.sitesById[state.siteId]);
      ET.Maps.drawCandidates(siteRes().candidates, data.candById, { select: selectCandidate, hover: hoverCandidate });
      maps.siteId = state.siteId;
    }
    ET.Maps.selectCandidate(state.candidateId, flyToCandidate && state.candidateId ? data.candById[state.candidateId] : null);
    ET.Maps.invalidate();
  }

  /* ------------------------------------------------------------ render */
  function renderHeaderTitles() {
    var m = mission(), s = data.sitesById[state.siteId];
    document.getElementById("target-kicker").textContent = m.body === "moon" ? "Target · Moon south pole" : "Target · Mars northern mid-latitudes";
    document.getElementById("target-title").textContent = s.name;
    var n = siteRes().counts;
    document.getElementById("earth-title").textContent = n.analog + " analogs · " + (n.low_match + n.rejected + n.cannot_evaluate) + " others";
  }

  function renderNav() {
    ET.Nav.setActive(state.route);
    document.body.classList.toggle("on-home", state.route === "home");
  }

  /** Background for the current page; world pages follow the selected world (cross-fade in CSS). */
  function renderWorld() {
    var world = state.missionId ? mission().body : "moon";
    document.body.dataset.world = world;
    var view = ROUTES[state.route].view;
    var bg = view === "home" ? null : view === "sources" ? "sources" : view === "planex" ? null : world;
    ET.Backdrop.show(bg);
  }

  function renderContent() {
    var view = ROUTES[state.route].view;
    if (view === "analogs") { renderHeaderTitles(); ET.Panels.renderSide(state, data); }
    if (view === "why") ET.Pages.renderWhy(state, data);
    if (view === "method") ET.Pages.renderMethod(state, data);
    if (view === "limits") ET.Pages.renderLimits(state, data);
    if (view === "sources") ET.Pages.renderSources(state, data);
    if (view === "planex") ET.Pages.renderPlanex(state, data);
    writeHash();
  }

  /** Show the view for state.route (called on every hash change). */
  function show(flyToCandidate) {
    var view = ROUTES[state.route].view;
    document.querySelectorAll(".view").forEach(function (v) { v.classList.toggle("active", v.id === "view-" + view); });
    renderNav();
    renderWorld();
    closeMenu();
    if (view === "home") ET.Solar.start(); else ET.Solar.stop();
    if (view === "analogs") syncMaps(flyToCandidate);
    renderContent();
  }

  function applyHash() {
    var h = parseHash();
    var prevRoute = state.route;
    state.route = h.route;
    var r = ROUTES[h.route];
    if (r.body) setMission(missionForBody(r.body).id, h.s);
    else if (h.m && data.missionsById[h.m] && data.missionsById[h.m].in_selector) setMission(h.m, h.s);
    else if (!state.missionId) setMission(missionForBody(storedWorld() === "mars" ? "mars" : "moon").id, h.s);
    if (r.view === "analogs") setCandidate(h.c || (prevRoute === h.route ? state.candidateId : null));
    show(Boolean(h.c));
    if (prevRoute !== h.route) window.scrollTo(0, 0);
  }

  /* ------------------------------------------------------------ actions */
  function selectSite(id) {
    state.siteId = id;
    setCandidate(state.candidateId);
    if (ROUTES[state.route].view === "analogs") syncMaps(false);
    renderContent();
  }

  function selectCandidate(id) {
    if (ROUTES[state.route].view !== "analogs") { go(routeForMission(mission()), { candidateId: id }); return; }
    setCandidate(id);
    renderContent();
    ET.Maps.selectCandidate(id, data.candById[id]);
  }

  function hoverCandidate(id, on) {
    ET.Maps.hoverCandidate(id, on);
    var li = document.querySelector('.rank-item[data-id="' + id + '"]');
    if (li) li.classList.toggle("hover", on);
  }

  function closeMenu() { ET.Nav.close(); }

  /* ------------------------------------------------------------ events */
  function onClick(e) {
    var t = e.target;
    var link = t.closest("[data-route]");
    if (link) { closeMenu(); if (link.dataset.route === state.route) { e.preventDefault(); show(false); } return; }
    var mBtn = t.closest("[data-mission]");
    if (mBtn && mBtn.dataset.mission !== state.missionId) { setMission(mBtn.dataset.mission); renderWorld(); renderContent(); return; }
    var item = t.closest(".rank-item");
    if (item) { selectCandidate(item.dataset.id); return; }
    if (t.closest("#back-list")) { state.candidateId = null; ET.Maps.selectCandidate(null); renderContent(); return; }
    if (t.closest("#open-why")) { go("why-not-others"); return; }
    var chip = t.closest("[data-why]");
    if (chip) { state.whyFilter = chip.dataset.why; renderContent(); return; }
    var openCand = t.closest("[data-open]");
    if (openCand) selectCandidate(openCand.dataset.open);
  }

  function bind() {
    document.addEventListener("click", onClick);
    document.addEventListener("change", function (e) { if (e.target.id === "site-select") selectSite(e.target.value); });
    document.addEventListener("input", function (e) {
      if (e.target.id === "src-search") { state.sourceQuery = e.target.value; renderContent(); }
    });
    document.addEventListener("keydown", function (e) {
      var item = e.target.closest && e.target.closest(".rank-item");
      if (item && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); selectCandidate(item.dataset.id); }
      if (e.key === "Escape") {
        closeMenu();
        if (state.candidateId && ROUTES[state.route].view === "analogs") { state.candidateId = null; ET.Maps.selectCandidate(null); renderContent(); }
      }
    });
    document.addEventListener("mouseover", function (e) {
      var item = e.target.closest && e.target.closest(".rank-item");
      if (item && maps.ready) ET.Maps.hoverCandidate(item.dataset.id, true);
    });
    document.addEventListener("mouseout", function (e) {
      var item = e.target.closest && e.target.closest(".rank-item");
      if (item && maps.ready) ET.Maps.hoverCandidate(item.dataset.id, false);
    });
    document.addEventListener("et:layerstatus", function () { if (state.route === "sources") ET.Pages.renderSources(state, data); });
    window.addEventListener("resize", function () { if (maps.ready) ET.Maps.invalidate(); });
    window.addEventListener("hashchange", applyHash);
  }

  /* ------------------------------------------------------------ boot */
  function index(arr) { var o = {}; arr.forEach(function (x) { o[x.id] = x; }); return o; }

  function boot() {
    ET.initTooltips();
    ET.Nav.init();
    ET.Backdrop.init();
    ET.Solar.init(document.getElementById("solar"), document.getElementById("solar-tip"), function (route) { go(route); });
    var files = ["missions", "targets", "features", "sources", "limitations", "earth_candidates", "results/artemis-iv", "results/skyfall", "coordinate_verification", "worlds"];
    Promise.all(files.map(function (f) { return ET.fetchJSON("data/" + f + ".json"); })).then(function (r) {
      data.missions = r[0].missions; data.missionsById = index(data.missions);
      data.targets = r[1]; data.sitesById = index(r[1].sites);
      data.features = r[2]; data.fdefs = index(r[2].features);
      data.sources = r[3].sources; data.sourcesById = index(data.sources);
      data.limitations = r[4];
      data.earth = r[5].candidates; data.candById = index(data.earth);
      data.results = { "artemis-iv": r[6], "skyfall": r[7] };
      data.coords = r[8];
      data.worlds = r[9];
      document.getElementById("sample-badge").hidden = !(r[6].contains_sample || r[7].contains_sample);
      bind();
      applyHash();
    }).catch(function (err) {
      var page = document.getElementById("page-planex");
      document.querySelectorAll(".view").forEach(function (v) { v.classList.toggle("active", v.id === "view-planex"); });
      ET.Solar.stop();
      page.innerHTML = '<div class="page-head"><div><h1>Could not load data</h1><p>' + ET.esc(err.message) +
        '</p><p class="muted">Serve the <span class="mono">web/</span> folder over HTTP (e.g. <span class="mono">python3 -m http.server 8000</span>) and run <span class="mono">python3 pipeline/compute_scores.py</span> first.</p></div></div>';
    });
  }

  boot();
})(window.ET);
