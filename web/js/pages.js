/* Full-width pages: WHY NOT OTHERS, METHOD, LIMITATIONS, SOURCES. */
(function (ET) {
  "use strict";

  var G = ET.Pages = {};
  var esc = ET.esc;

  function head(title, sub, right, kicker) {
    return '<div class="page-head"><div>' + (kicker ? '<span class="world-kicker">' + esc(kicker) + "</span>" : "") + "<h1>" + title + "</h1>" + (sub ? "<p>" + sub + "</p>" : "") + "</div>" + (right || "") + "</div>";
  }

  /** The selected world ("moon" | "mars") and its entry in worlds.json. */
  function worldOf(state, data) { return data.missionsById[state.missionId].body; }
  function worldInfo(state, data) { return ((data.worlds || {}).worlds || {})[worldOf(state, data)] || {}; }
  function worldSection(section, state, data) { return ((data.worlds || {})[section] || {})[worldOf(state, data)] || {}; }

  function worldNotes(notes) {
    if (!notes || !notes.length) return "";
    return '<div class="world-notes">' + notes.map(function (n) { return "<p>" + esc(n.text) + (n.status ? " " + ET.statusBadge(n.status) : "") + "</p>"; }).join("") + "</div>";
  }

  function ctxLine(state, data) {
    var m = data.missionsById[state.missionId], s = data.sitesById[state.siteId];
    return esc(m.name) + " · target: " + esc(s.name);
  }

  /** MOON | MARS segmented switch for the content pages (Moon = Artemis IV, Mars = SkyFall). */
  function ctxSwitch(state, data) {
    return '<div class="ctx-switch" role="group" aria-label="World">' + data.missions.filter(function (m) { return m.in_selector; }).map(function (m) {
      return '<button data-mission="' + esc(m.id) + '" aria-pressed="' + (m.id === state.missionId) + '" title="' + esc(m.name) + '">' + (m.body === "moon" ? "Moon" : "Mars") + "</button>";
    }).join("") + "</div>";
  }

  /* ================================================== WHY NOT OTHERS */
  function numbersTable(rows, data) {
    if (!rows || !rows.length) return '<span class="faint">—</span>';
    var hasLimit = rows.some(function (r) { return r.limit; });
    return '<table class="nums"><thead><tr><th>Feature</th><th>Target</th><th>Earth</th>' + (hasLimit ? "<th>Limit</th>" : "") + "</tr></thead><tbody>" +
      rows.map(function (r) {
        return "<tr><td>" + ET.Panels.featureLabel(r.feature_id, data) + "</td><td>" + esc(r.target) + "</td><td>" + esc(r.earth) + " " + ET.statusBadge(r.earth_status) + "</td>" +
          (hasLimit ? "<td>" + esc(r.limit || "") + "</td>" : "") + "</tr>";
      }).join("") + "</tbody></table>" +
      '<div class="faint" style="font-size:11px;margin-top:4px">Sources: ' + rows.map(function (r) {
        return [r.target_source_id, r.earth_source_id].filter(Boolean).map(function (id) { return ET.Panels.srcLink(id, data); }).join(" · ");
      }).filter(Boolean).join(" · ") + "</div>";
  }

  function weakest(rows, data) {
    if (!rows || !rows.length) return '<span class="faint">Not applicable</span>';
    return rows.map(function (r) {
      var s = r.similarity === null || r.similarity === undefined ? 0 : r.similarity;
      return '<div class="mini"><span>' + ET.Panels.featureLabel(r.feature_id, data) + ' <span class="faint">' + esc(r.target) + " vs " + esc(r.earth) + '</span></span><div class="bar grey"><i style="width:' + Math.round(s * 100) + '%"></i></div><span class="num">' + Math.round(s * 100) + "%</span></div>";
    }).join("");
  }

  G.renderWhy = function (state, data) {
    var siteRes = data.results[state.missionId].sites[state.siteId];
    var others = siteRes.candidates.filter(function (e) { return e.group !== "analog"; });
    var filter = state.whyFilter || "all";
    var shown = others.filter(function (e) { return filter === "all" || e.group === filter; });
    var counts = siteRes.counts;
    var chips = '<div class="chips" role="group" aria-label="Filter">' +
      [["all", "All " + others.length], ["rejected", "Rejected " + counts.rejected], ["low_match", "Low match " + counts.low_match], ["cannot_evaluate", "Cannot be evaluated " + counts.cannot_evaluate]]
        .map(function (c) { return '<button class="chip" data-why="' + c[0] + '" aria-pressed="' + (filter === c[0]) + '">' + esc(c[1]) + "</button>"; }).join("") + "</div>";
    var cards = shown.map(function (e) {
      var c = data.candById[e.id], k = e.card;
      var vClass = k.verdict.split(" ")[0];
      return '<article class="card">' +
        '<div class="row"><span class="label">1 · Verdict</span><div><div class="verdict ' + esc(vClass) + '">' + esc(k.verdict) + "</div><h3>" + esc(c.name) + '</h3><div class="faint" style="font-size:12px">' + esc(c.country) + (c.is_baseline ? " · baseline analog" : "") + (e.score_pct !== null ? " · score " + e.score_pct + "%" : "") + "</div></div></div>" +
        '<p style="margin:0;font-size:14px">' + esc(k.headline) + "</p>" +
        '<div class="row"><span class="label">2 · Reason type</span><span>' + (k.reason_type === "hard-filter fail" ? ET.term("hard filter", "Hard-filter fail") : esc(k.reason_type.charAt(0).toUpperCase() + k.reason_type.slice(1))) + "</span></div>" +
        '<div class="row"><span class="label">3 · The numbers</span><div>' + numbersTable(k.numbers, data) + "</div></div>" +
        '<div class="row"><span class="label">4 · Weakest 3</span><div>' + weakest(k.weakest, data) + "</div></div>" +
        '<div class="row"><span class="label">5 · What would change this</span><span>' + esc(k.what_would_change) + "</span></div>" +
        '<div class="row"><span class="label">6 · Confidence</span><span>' + ET.dots(k.confidence) + " " + esc(k.confidence) + ' <span class="faint" style="font-size:12px">— ' + esc(k.confidence_reason) + "</span></span></div>" +
        '<button class="back" data-open="' + esc(e.id) + '" style="margin:0;align-self:flex-start">Show on map →</button>' +
        "</article>";
    }).join("");
    document.getElementById("page-why").innerHTML =
      head("Why not others?", esc(worldSection("whyNot", state, data).intro || "") + " " + ctxLine(state, data) + ". Every Earth place that is not a top analog gets the same six-part explanation.", '<div class="head-right">' + ctxSwitch(state, data) + chips + "</div>", worldInfo(state, data).kicker) +
      (shown.length ? '<div class="cards">' + cards + "</div>" : '<p class="muted">Nothing in this group.</p>');
  };

  /* ================================================== METHOD */
  G.renderMethod = function (state, data) {
    var res = data.results[state.missionId];
    var m = res.method;
    var mission = data.missionsById[state.missionId];
    var siteRes = res.sites[state.siteId];
    var cats = data.features.categories;

    var nEarth = data.earth.length;
    var renorm = siteRes.weights_renormalised || {};
    var weightRows = cats.map(function (cat) {
      var feats = m.features.filter(function (f) { return data.fdefs[f].category === cat.id; });
      if (!feats.length) return "<tr><td>" + esc(cat.label) + '</td><td class="num">' + (m.weights_pct[cat.id] || 0) + '%</td><td colspan="4"><span class="faint">no features</span></td></tr>';
      return feats.map(function (f, i) {
        var r = renorm[f] || {};
        return "<tr>" + (i === 0 ? '<td rowspan="' + feats.length + '">' + esc(cat.label) + '</td><td class="num" rowspan="' + feats.length + '">' + (m.weights_pct[cat.id] || 0) + "%</td>" : "") +
          "<td>" + ET.Panels.featureLabel(f, data) + '</td><td class="num">' + (siteRes.weights_nominal[f] * 100).toFixed(1) + '%</td><td class="num">' +
          (r.has_target ? "<b>" + (r.weight * 100).toFixed(1) + "%</b>" : '<span class="faint">0% · no target value</span>') +
          '</td><td class="num">' + (r.earth_sites_with_data === undefined ? "—" : r.earth_sites_with_data + " / " + nEarth) + "</td></tr>";
      }).join("");
    }).join("");

    var scaleRows = m.features.filter(function (f) { return m.scales[f] !== undefined; }).map(function (f) {
      var d = data.fdefs[f];
      return "<tr><td>" + ET.Panels.featureLabel(f, data) + '</td><td class="num">' + esc(m.scales[f]) + " " + esc(d.unit || "") + "</td><td>" + esc(d.earth_method) + "</td></tr>";
    }).join("");

    var catRows = Object.keys(m.categorical_similarity).map(function (fid) {
      return "<tr><td>" + ET.Panels.featureLabel(fid, data) + "</td><td>" + m.categorical_similarity[fid].map(function (p) {
        return esc(p[0].replace(/_/g, " ")) + " ↔ " + esc(p[1].replace(/_/g, " ")) + ' <span class="num faint">' + p[2] + "</span>";
      }).join("<br>") + "</td></tr>";
    }).join("");

    /** NASA's own TBD marking, read from the mission package (null = not known). */
    function tbdBadge(c) {
      if (!("tbd_by_nasa" in c)) return "";
      if (c.tbd_by_nasa === true) return ' <span class="badge verify" data-tip="NASA marks this limit TBD in the mission package.">TBD by NASA</span>';
      if (c.tbd_by_nasa === null || c.tbd_by_nasa === undefined) return ' <span class="badge todo" data-tip="Not known whether NASA marks this TBD.">TBD ?</span>';
      return "";
    }
    var filterRows = (mission.constraints || []).map(function (c) {
      var lim = c.limit === null ? '<span class="badge todo">TODO</span>' : esc(Array.isArray(c.limit) ? c.limit.join("–") : c.limit) + " " + esc(c.unit || "");
      return "<tr><td>" + (c.feature_id ? ET.Panels.featureLabel(c.feature_id, data) : esc(c.id)) + "</td><td>" + esc(c.op) + " " + lim + (c.scale ? ' <span class="faint">at ' + esc(c.scale) + "</span>" : "") +
        "</td><td>" + (!c.hard_filter ? "No" : c.earth_applicable === false ? '<span class="badge todo" data-tip="No Earth data in the same variable and unit, so this filter cannot be applied to Earth sites.">Not applied to Earth</span>' : "Yes") +
        (c.label ? '<div class="faint" style="font-size:11px">' + esc(c.label) + "</div>" : "") + "</td><td>" + ET.statusBadge(c.status) + tbdBadge(c) +
        "</td><td>" + esc(c.note || "") + (c.package_text ? '<div class="faint" style="font-size:11px" data-tip="' + esc(c.checked || "") + '">NASA package: ' + esc(c.package_text) + "</div>" : "") + (c.source_id ? '<div class="faint" style="font-size:11px">' + ET.Panels.srcLink(c.source_id, data) + "</div>" : "") + "</td></tr>";
    }).join("");

    var valRows = Object.keys(res.sites).map(function (sid) {
      var s = res.sites[sid];
      return "<tr><td>" + esc(data.sitesById[sid].name) + "</td>" + s.validation.map(function (v) {
        var txt = v.status === "ranked" ? "#" + v.rank + " of " + v.of + " (" + v.score_pct + "%)" : v.status.replace("_", " ");
        return "<td>" + esc(txt) + "</td>";
      }).join("") + "</tr>";
    }).join("");
    var valHead = siteRes.validation.map(function (v) { return "<th>" + esc(data.candById[v.id].name) + "</th>"; }).join("");

    var sens = siteRes.sensitivity;
    var names = data.candById;
    var top1 = siteRes.candidates.find(function (e) { return e.rank === 1; });
    var sensRows = sens.scenarios.map(function (s) {
      var label = cats.find(function (c) { return c.id === s.category; }).label;
      return "<tr><td>" + esc(label) + " " + (s.delta_pp > 0 ? "+" : "") + s.delta_pp + ' pp</td><td class="num">' + esc(Object.keys(s.weights_pct).map(function (k) { return k.slice(0, 4) + " " + Math.round(s.weights_pct[k]); }).join(" · ")) +
        "</td><td>" + (s.top1_same ? "Same" : "→ " + esc(s.top1 ? names[s.top1].name : "—")) + "</td><td>" +
        (s.topn_changes.length ? s.topn_changes.map(function (id) { return esc(names[id].name); }).join(", ") : "None") + '</td><td class="num">' + s.max_rank_shift + "</td></tr>";
    }).join("");

    document.getElementById("page-method").innerHTML =
      head("Method", ctxLine(state, data) + ". How the " + ET.term("Similarity Score") + " is computed. Settings live in <span class=\"mono\">pipeline/config.json</span>; re-run the pipeline after editing.", ctxSwitch(state, data), worldInfo(state, data).kicker) +
      '<section class="block"><h2>1 · Two stages</h2><p>Stage A removes Earth places that break a mission ' + ET.term("hard filter") + '. Stage B scores the rest. Only features with data on <b>both</b> sides count; the remaining weights are ' + ET.term("renormalised") + ' and shown on every result.</p>' +
      '<div class="formula">Score = Σ wᵢ × similarityᵢ<br>similarityᵢ = exp( −|Earth − target| / scaleᵢ )</div>' +
      '<p style="margin-top:14px">If the target is a range (e.g. slope 0–15°), similarity is 100% inside the range and falls off with the distance to the nearest edge. Categories (rock type, regolith) use the table below. An Earth place with no perennial ground ice (none or seasonal frost only) counts as a full mismatch on depth-to-ice. It is called a <b>Similarity Score</b>, not accuracy: there is no ground truth for the Moon or Mars.</p></section>' +
      '<section class="block"><h2>2 · Weights</h2>' + weightsLine(cats, m.weights_pct) + worldNotes(worldSection("method", state, data).notes) + '<p>Provisional, from the team document. Each category is split equally between its features (<b>planned</b>). Features without a value for this target site are dropped and the rest are rescaled to 100% (<b>renormalised</b>, used for every Earth site here). Each Earth site is renormalised again over the features it has; its own weights are shown on its detail view. The last column shows how many Earth sites have a real value.</p><table class="grid"><thead><tr><th>Category</th><th>Weight</th><th>Feature</th><th>Planned</th><th>Renormalised for ' + esc(data.sitesById[state.siteId].name) + '</th><th>Earth sites with data</th></tr></thead><tbody>' + weightRows + "</tbody></table></section>" +
      '<section class="block"><h2>3 · Hard filters and mission limits</h2><p>Only rows with “Yes” remove Earth places. A limit that is not in the team documents stays TODO and is not applied.</p><table class="grid"><thead><tr><th>Feature</th><th>Limit</th><th>Filter</th><th>Status</th><th>Note · source</th></tr></thead><tbody>' + filterRows + "</tbody></table>" +
      (mission.constraints_note ? '<p class="faint" style="margin-top:10px">' + esc(mission.constraints_note) + "</p>" : "") + "</section>" +
      '<section class="block"><h2>4 · Scales and how Earth values are made</h2><p>PROVISIONAL, team to confirm. A difference equal to the scale gives 37% similarity; half the scale gives 61%.</p><table class="grid"><thead><tr><th>Feature</th><th>Scale</th><th>Earth-side method</th></tr></thead><tbody>' + scaleRows + "</tbody></table>" +
      '<h3 style="margin:22px 0 8px;font-size:16px">Category similarity (same category = 100%, unlisted pairs = 0%)</h3><table class="grid"><tbody>' + catRows + "</tbody></table></section>" +
      '<section class="block"><h2>5 · Validation: where known analogs land</h2><p>If the model is sensible, well-known analogs should not end up at the bottom. With SAMPLE Earth data this only checks that the machinery works.</p><table class="grid"><thead><tr><th>Target site</th>' + valHead + "</tr></thead><tbody>" + valRows + "</tbody></table></section>" +
      '<section class="block"><h2>6 · Sensitivity: weights ±' + sens.delta_pp + ' percentage points</h2><p>Each category weight moves by ±' + sens.delta_pp + ' pp; the others are rescaled to keep 100%. Current #1: <b>' + esc(top1 ? names[top1.id].name : "—") + "</b>. Top-1 is " + (sens.top1_stable ? "<b>stable</b> in every scenario." : "<b>not stable</b>: see below.") + '</p><table class="grid"><thead><tr><th>Change</th><th>New weights (%)</th><th>#1</th><th>Leaves / enters top ' + res.method.thresholds.top_n_analogs + '</th><th>Max rank shift</th></tr></thead><tbody>' + sensRows + "</tbody></table></section>" +
      '<section class="block"><h2>7 · Confidence</h2><p><b>High</b>: ≥' + Math.round(res.method.thresholds.confidence_high * 100) + "% of planned weight has data on both sides and no SAMPLE values. <b>Medium</b>: ≥" + Math.round(res.method.thresholds.confidence_medium * 100) + "%. <b>Low</b>: less, or any SAMPLE value, or the target site itself has data for under " + Math.round(res.method.thresholds.confidence_medium * 100) + "% of the weight. Low-confidence real values lower it one step. Places with less than " + Math.round(res.method.thresholds.min_earth_coverage * 100) + "% Earth coverage, or a hard filter that cannot be checked, are “Cannot be evaluated”.</p>" +
      '<p class="mono faint">python3 pipeline/compute_scores.py   # re-computes everything in web/data/results/</p></section>';
  };

  /** "Terrain 30 · Temperature 15 · …" built from the config weights (never typed). */
  function weightsLine(cats, pct) {
    return '<p class="weights-line">' + cats.map(function (c) { return esc(c.label) + " " + (pct[c.id] || 0); }).join(" · ") + "</p>";
  }

  /* ================================================== LIMITATIONS */
  G.renderLimits = function (state, data) {
    var mission = data.missionsById[state.missionId];
    var u = data.limitations.universal;
    var key = worldSection("limitations", state, data).universal_key || mission.body;
    function lims(arr) {
      return '<div class="lim-list">' + arr.map(function (l) {
        return '<div class="lim"><h3>' + esc(l.title) + (l.earth_can ? '<span class="badge">' + (l.earth_can === "No" ? "Earth cannot" : "Earth partly") + "</span>" : "") + "</h3><p>" + esc(l.text) + "</p>" +
          (l.source_id ? '<div class="faint" style="font-size:11px;margin-top:6px">' + ET.Panels.srcLink(l.source_id, data) + "</div>" : "") + "</div>";
      }).join("") + "</div>";
    }
    var siteRes = data.results[state.missionId].sites[state.siteId];
    var rows = siteRes.candidates.filter(function (e) { return e.group === "analog" || data.candById[e.id].is_baseline; }).map(function (e) {
      var l = e.limitations;
      function j(a) { return a.length ? a.map(esc).join(", ") : '<span class="faint">—</span>'; }
      return "<tr><td>" + esc(data.candById[e.id].name) + '<div class="faint" style="font-size:11px">' + esc(e.group.replace("_", " ")) + (e.score_pct !== null ? " · " + e.score_pct + "%" : "") + "</div></td><td>" + j(l.reproduces) + "</td><td>" + j(l.partly) + "</td><td>" + j(l.fails) + '</td><td class="faint">' + j(l.no_data) + "</td></tr>";
    }).join("");
    document.getElementById("page-limits").innerHTML =
      head("Honest limitations", "What an Earth analog can and cannot tell us about " + esc(mission.body === "moon" ? "the lunar south pole" : "the SkyFall regions on Mars") + ". This page is part of the result, not a disclaimer.", ctxSwitch(state, data), worldInfo(state, data).kicker) +
      '<section class="block"><h2>What no place on Earth can copy</h2>' + lims(u[key] || []) + "</section>" +
      '<section class="block"><h2>Per analog · ' + esc(data.sitesById[state.siteId].name) + '</h2><p>“Reproduces” = similarity ≥70%; “Partly” = 40–70%; “Fails” = under 40%. Generated from the scores. Top analogs and baselines are listed.</p><table class="grid"><thead><tr><th>Earth place</th><th>Reproduces</th><th>Partly</th><th>Fails</th><th>No data</th></tr></thead><tbody>' + rows + "</tbody></table></section>" +
      '<section class="block"><h2>Limits of the method</h2>' + lims(u.method) + "</section>";
  };

  /* ================================================== PLANEX */
  /* Content moved from the team's About page (frontend/js/pages/about.js). The technical-approach paragraph
   * is updated to describe this static app instead of the earlier FastAPI version. */
  G.renderPlanex = function () {
    document.getElementById("page-planex").innerHTML =
      head("PLANEX", "Team PLANEX · NASA Space Apps Challenge 2026") +
      '<section class="block"><h2>About EarthTwin</h2><p>EarthTwin is a scientific decision-support prototype built by team <b>PLANEX</b> for the NASA Space Apps Challenge 2026, challenge <em>“Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars”</em>.</p></section>' +
      '<section class="block"><h2>Purpose</h2><p>Mission teams test rovers, drills, habitats and procedures at terrestrial analog sites before flight, but those sites are often characterised unevenly. EarthTwin helps researchers answer four questions: which Earth locations share relevant characteristics with a chosen lunar or Martian region; what measured evidence supports each match; how similar the environments are and where they differ; and which locations may suit equipment testing, terrain navigation or geological investigation.</p></section>' +
      '<section class="block"><h2>Technical approach</h2><ul>' +
      "<li><b>Data pipeline:</b> Python scripts read open NASA, USGS and other agency data (LOLA, HRSC-MOLA, NASADEM, MODIS and more), record the provenance of every value and pre-compute the scores as JSON.</li>" +
      "<li><b>Website:</b> a static site in plain HTML, CSS and JavaScript with Leaflet maps (NASA Trek, GIBS and USGS tiles). No backend and no build step.</li>" +
      "<li><b>Method:</b> hard filters, then a weighted Similarity Score over features measured the same way on both sides. See the Method tab.</li></ul></section>" +
      '<section class="block"><h2>Acknowledgments</h2><p>Basemap imagery: NASA Solar System Treks and NASA GIBS; USGS Astrogeology map services. Mapping library: Leaflet (BSD-2-Clause). All data sources are listed on the <a href="#sources" data-route="sources">Sources</a> page.</p></section>' +
      '<section class="block"><h2>Independence</h2><p>EarthTwin is an independent team project created for the NASA Space Apps Challenge. It is not affiliated with, endorsed by or an official product of NASA or any other agency or institution. The use of NASA data and imagery does not imply endorsement.</p></section>' +
      '<section class="block"><h2>Team</h2><p>Team PLANEX. Contributor names are maintained by the team in the repository README.</p></section>';
  };

  /* ================================================== SOURCES */
  function usedSourceIds(data) {
    var used = {};
    data.targets.sites.forEach(function (s) {
      Object.values(s.features || {}).forEach(function (m) { if (m.source_id) used[m.source_id] = 1; });
      (s.facts || []).forEach(function (f) { if (f.source_id) used[f.source_id] = 1; });
      if (s.position && s.position.source_id) used[s.position.source_id] = 1;
    });
    Object.values(data.targets.defaults || {}).forEach(function (d) { Object.values(d).forEach(function (m) { if (m && m.source_id) used[m.source_id] = 1; }); });
    data.missions.forEach(function (m) { (m.sources || []).forEach(function (id) { used[id] = 1; }); (m.constraints || []).forEach(function (c) { if (c.source_id) used[c.source_id] = 1; }); });
    data.earth.forEach(function (c) { Object.values(c.features).forEach(function (m) { if (m.source_id) used[m.source_id] = 1; }); });
    Object.values(ET.LAYERS).forEach(function (b) { b.base.concat(b.overlays).forEach(function (d) { used[d.source_id] = 1; }); });
    return used;
  }

  G.renderSources = function (state, data) {
    var q = (state.sourceQuery || "").toLowerCase();
    var used = usedSourceIds(data);
    var groups = [["nasa_usgs", "NASA and USGS"], ["other_agency", "Other agencies, non-NASA (ESA, USDA)"], ["peer_reviewed", "Peer-reviewed papers and conference abstracts (NASA data, other publishers)"], ["third_party", "Third-party, non-NASA: open data services, news, blogs, Wikipedia/Wikidata"], ["team_doc", "Team documents"], ["method", "Method choices"], ["sample", "Placeholders"]];
    var html = groups.map(function (g) {
      var items = data.sources.filter(function (s) { return s.kind === g[0] && (!q || (s.name + " " + (s.url || "") + " " + s.id).toLowerCase().indexOf(q) >= 0); });
      if (!items.length) return "";
      return '<section class="block"><h2>' + esc(g[1]) + ' <span class="faint num" style="font-size:16px">' + items.length + "</span></h2>" + items.map(function (s) {
        return '<div class="src' + (used[s.id] ? " used" : "") + '"><span class="name">' + (s.url ? '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.name) + "</a>" : esc(s.name)) + "</span>" +
          '<span class="badge">' + esc((s.access || "").replace(/_/g, " ")) + "</span>" +
          '<span class="meta">id: ' + esc(s.id) + (s.note ? " · " + esc(s.note) : "") + (used[s.id] ? "" : " · not used by any value yet") + "</span></div>";
      }).join("") + "</section>";
    }).join("");
    document.getElementById("page-sources").innerHTML =
      head("Sources", "● = used by at least one value in the app. NASA/USGS sources are kept separate from third-party sources. ‘Access’ says how much of each source the team actually read.",
        '<input class="search" id="src-search" type="search" placeholder="Filter sources…" value="' + esc(state.sourceQuery || "") + '" aria-label="Filter sources">') +
      coordinateReport(data) + layerReport() + assetCredits() + html;
    var input = document.getElementById("src-search");
    if (state.sourceQuery) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
  };

  /** Coordinate verification table (written by pipeline/fetch_context_data.py coords). */
  function coordinateReport(data) {
    var c = data.coords;
    if (!c || !c.rows) return "";
    var srcName = { gnis: "USGS GNIS", gvp: "Smithsonian GVP", wikidata: "Wikidata (third-party)", none: "—" };
    var fmt = function (a, b) { return a === "" || a === null || a === undefined ? "—" : Number(a).toFixed(4) + ", " + Number(b).toFixed(4); };
    var rows = c.rows.map(function (r) {
      var badgeClass = { verified: "solid", updated: "", unverified: "todo" }[r.status] || "";
      return "<tr><td>" + esc(r.name) + '</td><td class="num">' + fmt(r.old_lat, r.old_lon) + '</td><td class="num">' + fmt(r.verified_lat, r.verified_lon) +
        '</td><td class="num">' + (r.distance_km === "" ? "—" : esc(r.distance_km) + " km") + "</td><td>" + '<span class="badge ' + badgeClass + '">' + esc(r.status) + "</span>" +
        "</td><td>" + (r.source_url ? '<a href="' + esc(r.source_url) + '" target="_blank" rel="noopener">' + esc(srcName[r.source] || r.source) + " " + esc(r.ref_id) + "</a>" : esc(srcName[r.source] || "—")) +
        (r.point_type ? '<div class="faint" style="font-size:11px">' + esc(r.point_type) + "</div>" : "") + (r.note ? '<div class="faint" style="font-size:11px">' + esc(r.note) + "</div>" : "") +
        '</td><td><a href="' + esc(r.worldview_url) + '" target="_blank" rel="noopener">Worldview</a></td></tr>';
    }).join("");
    return '<section class="block"><h2>Coordinate check · Earth candidates</h2><p>Checked ' + esc(c.checked_on) + ". <b>verified</b> = the old position was within " + esc(c.tolerance_km) +
      " km of the reference; <b>updated</b> = moved to the reference point; <b>unverified</b> = no reference found, old assistant-typed position kept. Open Worldview to check each point visually.</p>" +
      '<table class="grid"><thead><tr><th>Candidate</th><th>Old</th><th>Verified</th><th>Moved</th><th>Status</th><th>Reference</th><th>Visual</th></tr></thead><tbody>' + rows + "</tbody></table></section>";
  }

  /** Credits for every visual asset in the interface (no stock images are shipped). */
  function assetCredits() {
    var rows = [
      ["Home solar system (Sun, planets, Moon, nebula, comets)", "Generated in the browser from seeded noise (web/js/solar-art.js, solar.js). No image files.", "Team PLANEX, procedural"],
      ["Page backgrounds: Moon, Mars, Sources, base star field", "Generated in the browser (web/js/backdrop.js), drawn from written descriptions of the team's reference images. No image files.", "Team PLANEX, procedural"],
      ["Moon map base: LROC WAC mosaic, natural greys", "NASA/ASU LROC via USGS Astrogeology WMS, with a light CSS grade (grayscale, slight warm tint).", "NASA / USGS, public domain"],
      ["Globe texture: Earth", "NASA Blue Marble Next Generation, 2048 × 1024 equirectangular, from NASA GIBS (WMS EPSG:4326). Stored as web/img/globe/earth_bluemarble_2048.jpg.", "NASA, public domain"],
      ["Globe texture: Moon", "LROC WAC global mosaic (USGS Astrogeology WMS, layer LROC_WAC), with the cap south of 74°S replaced by the USGS LOLA south-pole relief image already in the app (the WAC mosaic smears at the pole). web/img/globe/moon_lroc_wac_lola_2048.jpg.", "NASA/ASU LROC, NASA/GSFC LOLA, USGS; public domain"],
      ["Globe texture: Mars", "Viking MDIM 2.1 colour mosaic from NASA Mars Trek (the map fallback image, reused).", "NASA/USGS, public domain"],
      ["Typeface: Sora", "Self-hosted from Google Fonts (web/fonts/), SIL Open Font License 1.1 (web/fonts/OFL-Sora.txt).", "The Sora Project Authors"]
    ];
    return '<section class="block"><h2>Visual assets</h2><table class="grid"><thead><tr><th>Asset</th><th>How it is made</th><th>Credit · licence</th></tr></thead><tbody>' +
      rows.map(function (r) { return "<tr><td>" + esc(r[0]) + "</td><td>" + esc(r[1]) + "</td><td>" + esc(r[2]) + "</td></tr>"; }).join("") + "</tbody></table></section>";
  }

  function layerReport() {
    var rows = [];
    Object.keys(ET.LAYERS).forEach(function (body) {
      var b = ET.LAYERS[body];
      b.base.concat(b.overlays).forEach(function (d) {
        var st = ET.layerStatus[d.id];
        var live = st ? { ok: "Tiles OK", blank: "BLANK → fallback", error: "Error → fallback", unverifiable: "Loads, pixels unreadable" }[st.state] : "Not checked yet (open that map)";
        rows.push("<tr><td>" + esc(body) + "</td><td>" + esc(d.name) + '</td><td class="mono" style="word-break:break-all">' + esc(d.url.split("?")[0].replace("https://", "")) + (d.layers ? " · " + esc(d.layers) : "") + "</td><td>Verified 2026-11-09</td><td>" + esc(live) + "</td></tr>");
      });
      rows.push("<tr><td>" + esc(body) + "</td><td>" + esc(b.fallback.name) + '</td><td class="mono">' + esc(b.fallback.url) + "</td><td>Bundled file</td><td>Always available</td></tr>");
    });
    return '<section class="block"><h2>Map layers</h2><p>Each layer was tested before release (HTTP 200, CORS header, non-blank pixels). In the browser, each base layer is checked again: a blank or failing layer is replaced by a clearly marked static image.</p>' +
      '<table class="grid"><thead><tr><th>Map</th><th>Layer</th><th>Service</th><th>Pre-release check</th><th>Live check now</th></tr></thead><tbody>' + rows.join("") + "</tbody></table></section>";
  }
})(window.ET);
