/* App wiring: load data, keep state (also in the URL hash), render, handle clicks. */
(function (ET) {
  "use strict";

  var data = {};
  var state = { missionId: null, siteId: null, candidateId: null, tab: "analogs", whyFilter: "all", sourceQuery: "" };

  /* ------------------------------------------------------------ url state */
  function readHash() {
    var h = {};
    location.hash.replace(/^#/, "").split("&").forEach(function (kv) {
      var p = kv.split("=");
      if (p[0]) h[p[0]] = decodeURIComponent(p[1] || "");
    });
    return h;
  }
  function writeHash() {
    var parts = ["m=" + state.missionId, "s=" + state.siteId, "t=" + state.tab];
    if (state.candidateId) parts.push("c=" + state.candidateId);
    history.replaceState(null, "", "#" + parts.join("&"));
  }

  /* ------------------------------------------------------------ render */
  function mission() { return data.missionsById[state.missionId]; }
  function siteRes() { return data.results[state.missionId].sites[state.siteId]; }

  function renderSwitch() {
    var el = document.getElementById("mission-switch");
    el.innerHTML = data.missions.filter(function (m) { return m.in_selector; }).map(function (m) {
      return '<button data-mission="' + ET.esc(m.id) + '" aria-pressed="' + (m.id === state.missionId) + '">' + ET.esc(m.name) + "</button>";
    }).join("");
  }

  function renderHeaderTitles() {
    var m = mission(), s = data.sitesById[state.siteId];
    document.getElementById("target-kicker").textContent = m.body === "moon" ? "Target · Moon south pole" : "Target · Mars northern mid-latitudes";
    document.getElementById("target-title").textContent = s.name;
    var n = siteRes().counts;
    document.getElementById("earth-title").textContent = n.analog + " analogs · " + (n.low_match + n.rejected + n.cannot_evaluate) + " others";
  }

  function render() {
    renderSwitch();
    renderHeaderTitles();
    document.querySelectorAll(".tabs button").forEach(function (b) { b.setAttribute("aria-selected", b.dataset.tab === state.tab ? "true" : "false"); });
    document.querySelectorAll(".view").forEach(function (v) { v.classList.toggle("active", v.id === "view-" + state.tab); });
    if (state.tab === "analogs") ET.Panels.renderSide(state, data);
    if (state.tab === "why") ET.Pages.renderWhy(state, data);
    if (state.tab === "method") ET.Pages.renderMethod(state, data);
    if (state.tab === "limits") ET.Pages.renderLimits(state, data);
    if (state.tab === "sources") ET.Pages.renderSources(state, data);
    writeHash();
  }

  function sitesOfMission(m) {
    return m.target_site_ids.concat(m.reference_site_ids || []).map(function (id) { return data.sitesById[id]; });
  }

  function applyMission(missionId, siteId) {
    state.missionId = missionId;
    var m = mission();
    state.siteId = siteId && m.target_site_ids.concat(m.reference_site_ids || []).indexOf(siteId) >= 0 ? siteId : m.default_site_id;
    state.candidateId = null;
    ET.Maps.setMission(m, sitesOfMission(m), selectSite);
    applySite(state.siteId, true);
  }

  function applySite(siteId, skipRender) {
    state.siteId = siteId;
    if (state.candidateId && !siteRes().candidates.some(function (e) { return e.id === state.candidateId; })) state.candidateId = null;
    ET.Maps.selectSite(data.sitesById[siteId]);
    ET.Maps.drawCandidates(siteRes().candidates, data.candById, { select: selectCandidate, hover: hoverCandidate });
    if (state.candidateId) ET.Maps.selectCandidate(state.candidateId, null);
    render();
  }

  function selectSite(id) { applySite(id); }

  function selectCandidate(id) {
    state.candidateId = id;
    if (state.tab !== "analogs") { state.tab = "analogs"; render(); ET.Maps.invalidate(); }
    else render();
    ET.Maps.selectCandidate(id, data.candById[id]);
  }

  function hoverCandidate(id, on) {
    ET.Maps.hoverCandidate(id, on);
    var li = document.querySelector('.rank-item[data-id="' + id + '"]');
    if (li) li.classList.toggle("hover", on);
  }

  /* ------------------------------------------------------------ events */
  function bind() {
    document.addEventListener("click", function (e) {
      var t = e.target;
      var mBtn = t.closest("[data-mission]");
      if (mBtn && mBtn.dataset.mission !== state.missionId) { applyMission(mBtn.dataset.mission); return; }
      var tab = t.closest(".tabs button");
      if (tab) {
        state.tab = tab.dataset.tab;
        document.getElementById("tabs").classList.remove("open");
        document.getElementById("menu-btn").setAttribute("aria-expanded", "false");
        render();
        if (state.tab === "analogs") ET.Maps.invalidate();
        window.scrollTo(0, 0);
        return;
      }
      if (t.closest("#menu-btn")) {
        var open = document.getElementById("tabs").classList.toggle("open");
        t.closest("#menu-btn").setAttribute("aria-expanded", open ? "true" : "false");
        return;
      }
      var item = t.closest(".rank-item");
      if (item) { selectCandidate(item.dataset.id); return; }
      if (t.closest("#back-list")) { state.candidateId = null; ET.Maps.selectCandidate(null); render(); return; }
      if (t.closest("#open-why")) { state.tab = "why"; render(); return; }
      var chip = t.closest("[data-why]");
      if (chip) { state.whyFilter = chip.dataset.why; render(); return; }
      var open = t.closest("[data-open]");
      if (open) { selectCandidate(open.dataset.open); return; }
    });
    document.addEventListener("change", function (e) {
      if (e.target.id === "site-select") applySite(e.target.value);
    });
    document.addEventListener("input", function (e) {
      if (e.target.id === "src-search") { state.sourceQuery = e.target.value; render(); }
    });
    document.addEventListener("keydown", function (e) {
      var item = e.target.closest && e.target.closest(".rank-item");
      if (item && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); selectCandidate(item.dataset.id); }
      if (e.key === "Escape" && state.candidateId) { state.candidateId = null; render(); }
    });
    document.addEventListener("mouseover", function (e) {
      var item = e.target.closest && e.target.closest(".rank-item");
      if (item) ET.Maps.hoverCandidate(item.dataset.id, true);
    });
    document.addEventListener("mouseout", function (e) {
      var item = e.target.closest && e.target.closest(".rank-item");
      if (item) ET.Maps.hoverCandidate(item.dataset.id, false);
    });
    document.addEventListener("et:layerstatus", function () { if (state.tab === "sources") ET.Pages.renderSources(state, data); });
    window.addEventListener("resize", ET.Maps.invalidate);
    window.addEventListener("hashchange", function () {
      var h = readHash();
      if (h.t && h.t !== state.tab) state.tab = h.t;
      if (h.m && h.m !== state.missionId && data.missionsById[h.m] && data.missionsById[h.m].in_selector) applyMission(h.m, h.s);
      else if (h.s && h.s !== state.siteId && data.sitesById[h.s]) applySite(h.s);
      else render();
      if (h.c && h.c !== state.candidateId) selectCandidate(h.c);
    });
  }

  /* ------------------------------------------------------------ boot */
  function index(arr) { var o = {}; arr.forEach(function (x) { o[x.id] = x; }); return o; }

  function boot() {
    ET.initTooltips();
    var files = ["missions", "targets", "features", "sources", "limitations", "earth_candidates", "results/artemis-iv", "results/skyfall"];
    Promise.all(files.map(function (f) { return ET.fetchJSON("data/" + f + ".json"); })).then(function (r) {
      data.missions = r[0].missions; data.missionsById = index(data.missions);
      data.targets = r[1]; data.sitesById = index(r[1].sites);
      data.features = r[2]; data.fdefs = index(r[2].features);
      data.sources = r[3].sources; data.sourcesById = index(data.sources);
      data.limitations = r[4];
      data.earth = r[5].candidates; data.candById = index(data.earth);
      data.results = { "artemis-iv": r[6], "skyfall": r[7] };
      document.getElementById("sample-badge").hidden = !(r[6].contains_sample || r[7].contains_sample);
      bind();
      ET.Maps.initEarth();
      var h = readHash();
      if (h.t) state.tab = h.t;
      if (h.c) state.candidateId = h.c;
      var start = data.missionsById[h.m] && data.missionsById[h.m].in_selector ? h.m : data.missions.filter(function (m) { return m.in_selector; })[0].id;
      var keepCand = state.candidateId;
      applyMission(start, h.s);
      if (keepCand && siteRes().candidates.some(function (e) { return e.id === keepCand; })) selectCandidate(keepCand);
    }).catch(function (err) {
      document.getElementById("side").innerHTML = '<div class="sec"><span class="label">Could not load data</span><p>' + ET.esc(err.message) +
        '</p><p class="muted">Serve the <span class="mono">web/</span> folder over HTTP (e.g. <span class="mono">python3 -m http.server 8000</span>) and run <span class="mono">python3 pipeline/compute_scores.py</span> first.</p></div>';
    });
  }

  boot();
})(window.ET);
