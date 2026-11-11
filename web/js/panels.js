/* Sidebar on the ANALOGS view: mission, target site, ranked analogs, and the per-feature comparison. */
(function (ET) {
  "use strict";

  var P = ET.Panels = {};
  var esc = ET.esc;

  function srcLink(id, data) {
    if (!id) return "";
    var s = data.sourcesById[id];
    if (!s) return esc(id);
    var label = esc(s.name.length > 60 ? s.name.slice(0, 57) + "…" : s.name);
    return s.url ? '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + label + "</a>" : label;
  }
  P.srcLink = srcLink;

  function featureLabel(fid, data) {
    var f = data.fdefs[fid];
    return f ? '<span data-tip="' + esc(f.tooltip + (f.caveat ? " " + f.caveat : "")) + '">' + esc(f.label) + "</span>" : esc(fid);
  }
  P.featureLabel = featureLabel;

  function missingText(reason) {
    return reason === "no_target_data" ? "No data on the target side" : reason === "no_earth_data" ? "No data on the Earth side" : "";
  }

  /* ------------------------------------------------------------ header + site */
  /** Plain heading so the user knows which interface is open. */
  function analogHeading(mission) {
    return '<div class="sec analog-head"><h1 class="analog-title">' + (mission.body === "moon" ? "Moon Analog · Artemis" : "Mars Analog · SkyFall") + "</h1></div>";
  }

  function siteBlock(mission, site, siteRes, data) {
    var opts = mission.target_site_ids.concat(mission.reference_site_ids || []).map(function (id) {
      var s = data.sitesById[id];
      var ref = (mission.reference_site_ids || []).indexOf(id) >= 0 ? " (reference, not a mission region)" : "";
      return '<option value="' + esc(id) + '"' + (id === site.id ? " selected" : "") + ">" + esc(s.name + ref) + "</option>";
    }).join("");
    var cov = siteRes.target_coverage;
    var flags = (site.flags || []).map(function (f) { return '<span class="badge">' + esc(f.replace(/_/g, " ")) + "</span>"; }).join("");
    return '<div class="sec">' +
      '<label class="label" for="site-select">Target site · ' + (mission.body === "moon" ? "Moon" : "Mars") + "</label>" +
      '<select class="site" id="site-select">' + opts + "</select>" +
      '<div class="site-meta">' + ET.statusBadge(site.status) + " " + '<span class="badge">' + esc(site.role.replace(/_/g, " ")) + "</span>" + flags + "</div>" +
      '<div class="coverage" data-tip="Share of the scoring weight for which this target site has a value in the team documents. Features without data are left out, never guessed.">Target data coverage <b class="num" style="color:#e9ecef">' + ET.pct(cov) + '</b><div class="meter"><i style="width:' + Math.round(cov * 100) + '%"></i></div></div>' +
      "</div>";
  }

  /* ------------------------------------------------------------ ranked list */
  function listBlock(siteRes, state, data) {
    var analogs = siteRes.candidates.filter(function (e) { return e.group === "analog"; });
    var items = analogs.map(function (e) {
      var c = data.candById[e.id];
      var tag = c.is_baseline ? '<span class="badge" data-tip="A well-known analog, shown as a baseline.">Baseline</span>' : '<span class="badge solid" data-tip="Not in the usual analog list.">New</span>';
      var stab = e.rank_range && e.rank_range[0] !== e.rank_range[1] ? "rank " + e.rank_range[0] + "–" + e.rank_range[1] + " under ±10 pp" : "rank stable under ±10 pp";
      return '<li class="rank-item' + (state.candidateId === e.id ? " selected" : "") + '" data-id="' + esc(e.id) + '" tabindex="0" role="button" aria-label="' + esc(c.name + ", similarity " + e.score_pct + "%") + '">' +
        '<div class="r">' + e.rank + "</div>" +
        '<div><div class="n">' + esc(c.name) + '</div><div class="c">' + esc(c.country) + " · " + ET.dots(e.confidence) + " " + esc(e.confidence) + "</div></div>" +
        '<div class="s num">' + e.score_pct + "<small>%</small></div>" +
        '<div class="bar"><i style="width:' + e.score_pct + '%"></i></div>' +
        '<div class="tags" style="grid-column:2/4;margin-top:4px">' + tag + ' <span class="faint" style="font-size:11px" data-tip="' + esc(ET.GLOSSARY.sensitivity) + '">' + esc(stab) + "</span></div>" +
        "</li>";
    }).join("");
    var n = siteRes.counts;
    var others = n.low_match + n.rejected + n.cannot_evaluate;
    return '<div class="sec">' +
      '<span class="label">Top ' + analogs.length + " Earth analogs · " + ET.term("Similarity Score") + "</span>" +
      (analogs.length ? '<ol class="rank-list">' + items + "</ol>" : '<p class="muted">No Earth place passes the filters with enough data.</p>') +
      '<button class="others-link" id="open-why"><span>Why not the other ' + others + "?</span><span>" + n.rejected + " rejected · " + n.low_match + " low · " + n.cannot_evaluate + " no data →</span></button>" +
      "</div>";
  }

  /* ------------------------------------------------------------ detail */
  var PROV_LABELS = [["dataset", "Dataset"], ["product_id", "Product"], ["version", "Version"], ["date_range", "Dates"],
    ["resolution", "Resolution"], ["processing", "Steps"], ["source_url", "URL"]];

  /** Tooltip text for one value: its note plus every provenance field the pipeline recorded. */
  function noteTip(m) {
    if (!m) return "";
    var parts = m.note ? [m.note] : [];
    var prov = m.provenance || {};
    PROV_LABELS.forEach(function (p) { if (prov[p[0]]) parts.push(p[1] + ": " + prov[p[0]]); });
    if (m.confidence) parts.push("Confidence: " + m.confidence);
    return parts.length ? ' data-tip="' + esc(parts.join("\n")) + '"' : "";
  }

  /** Context features: measured or derived, shown for transparency, never part of the score. */
  function contextRows(cand, data) {
    var ids = data.features.features.filter(function (f) { return f.context_only; }).map(function (f) { return f.id; });
    var rows = ids.map(function (fid) {
      var m = cand.features[fid], fd = data.fdefs[fid];
      var val = !m || m.value === null || m.value === undefined ? "No data" : String(m.value) + (fd.unit && typeof m.value === "number" ? " " + fd.unit : "");
      return '<div class="feat"><div class="feat-head"><span>' + featureLabel(fid, data) + '</span><span class="w">not scored</span></div>' +
        '<div class="feat-vals"><span><b' + noteTip(m) + ">" + esc(val) + "</b> " + ET.statusBadge(m ? m.status : "TODO") + "</span></div></div>";
    }).join("");
    return '<div class="sec"><span class="label">Context · measured but not scored</span><p class="faint" style="font-size:11px;margin:0 0 4px">Raw map classes, distances and proxies behind the scored values. A proxy in a different unit (ATI) is never compared with Mars.</p>' + rows + "</div>";
  }

  function featureRows(entry, siteRes, data) {
    var cand = data.candById[entry.id];
    return entry.features.map(function (f) {
      var tNote = noteTip(siteRes.target_features[f.feature_id]);
      var eNote = noteTip(cand.features[f.feature_id]);
      var miss = f.similarity === null || f.similarity === undefined;
      var sim = miss ? 0 : f.similarity;
      var w = miss ? '<span class="w">not used</span>' :
        '<span class="w" data-tip="Weight after leaving out features without data (' + esc(ET.GLOSSARY.renormalised) + ')">weight ' + Math.round(f.weight_used * 100) + "%" +
        (Math.abs(f.weight_used - f.weight_nominal) > 0.001 ? " (planned " + Math.round(f.weight_nominal * 100) + "%)" : "") + "</span>";
      return '<div class="feat' + (miss ? " missing" : "") + '">' +
        '<div class="feat-head"><span>' + featureLabel(f.feature_id, data) + "</span>" + w + "</div>" +
        '<div class="feat-vals"><span>Target <b' + tNote + ">" + esc(f.target) + "</b> " + ET.statusBadge(f.target_status) + "</span>" +
        "<span>Earth <b" + eNote + ">" + esc(f.earth) + "</b> " + ET.statusBadge(f.earth_status) + "</span></div>" +
        (miss ? '<div class="faint" style="font-size:12px">' + esc(missingText(f.missing)) + "</div>" :
          '<div class="mini"><div class="bar"><i style="width:' + Math.round(sim * 100) + '%"></i></div><span class="faint" style="font-size:11px">similarity</span><span class="num">' + Math.round(sim * 100) + "%</span></div>") +
        "</div>";
    }).join("");
  }

  function detailBlock(entry, siteRes, data) {
    var c = data.candById[entry.id];
    var used = entry.features.filter(function (f) { return f.similarity !== null && f.similarity !== undefined; }).length;
    var lim = entry.limitations;
    function list(arr) { return arr.length ? arr.map(esc).join(", ") : '<span class="faint">—</span>'; }
    var card = entry.card;
    return '<div class="sec">' +
      '<button class="back" id="back-list">← All analogs</button>' +
      '<span class="label" style="display:block">' + esc(c.country) + (c.is_baseline ? " · baseline analog" : " · new candidate") + "</span>" +
      '<div class="detail-name">' + esc(c.name) + "</div>" +
      '<p class="muted" style="font-size:13px;margin:6px 0 0">' + esc(c.why_candidate) + "</p>" +
      '<div class="big-score"><b class="num">' + (entry.score_pct === null ? "—" : entry.score_pct + "%") + "</b><span>" + ET.term("Similarity Score") + (entry.rank ? " · rank " + entry.rank : "") + "</span></div>" +
      '<dl class="kv">' +
      "<dt>Confidence</dt><dd>" + ET.dots(entry.confidence) + " " + esc(entry.confidence) + "</dd>" +
      "<dt>Features compared</dt><dd>" + used + " of " + entry.features.length + "</dd>" +
      '<dt><span data-tip="Share of planned weight with data on the target side × on the Earth side.">Data coverage</span></dt><dd>' + ET.pct(entry.coverage.target * entry.coverage.earth) + "</dd>" +
      (entry.rank_range ? '<dt>' + ET.term("sensitivity", "Rank under ±10 pp") + "</dt><dd>" + entry.rank_range[0] + "–" + entry.rank_range[1] + "</dd>" : "") +
      "<dt>Position</dt><dd>" + c.lat.toFixed(2) + ", " + c.lon.toFixed(2) + " " + ET.statusBadge(c.position.status) + "</dd>" +
      "</dl>" +
      '<p class="faint" style="font-size:12px;margin:10px 0 0">Why this confidence: ' + esc(entry.confidence_reasons.join("; ")) + ".</p>" +
      (card ? '<div class="notice" style="margin-top:12px"><b>' + esc(card.verdict) + ".</b> " + esc(card.headline) + " " + esc(card.what_would_change) + "</div>" : "") +
      "</div>" +
      '<div class="sec"><span class="label">Feature by feature · target vs Earth</span><p class="faint" style="font-size:11px;margin:0 0 4px">Hover a value to see how it was obtained.</p>' + featureRows(entry, siteRes, data) + "</div>" +
      contextRows(c, data) +
      '<div class="sec"><span class="label">What this analog can and cannot test</span>' +
      '<div class="lim-grid"><div><span class="label">Reproduces</span>' + list(lim.reproduces) + '</div><div><span class="label">Partly</span>' + list(lim.partly) +
      '</div><div><span class="label">Fails</span>' + list(lim.fails) + "</div></div>" +
      (lim.no_data.length ? '<p class="faint" style="font-size:12px">No data: ' + list(lim.no_data) + "</p>" : "") +
      '<p class="faint" style="font-size:12px">Plus everything Earth cannot copy: see the Limitations tab.</p></div>';
  }

  /* ------------------------------------------------------------ render */
  P.renderSide = function (state, data) {
    var mission = data.missionsById[state.missionId];
    var site = data.sitesById[state.siteId];
    var siteRes = data.results[state.missionId].sites[state.siteId];
    var html = analogHeading(mission);
    html += siteBlock(mission, site, siteRes, data);
    var entry = state.candidateId && siteRes.candidates.find(function (e) { return e.id === state.candidateId; });
    html += entry ? detailBlock(entry, siteRes, data) : listBlock(siteRes, state, data);
    var side = document.getElementById("side");
    var keepScroll = entry ? 0 : side.scrollTop;
    side.innerHTML = html;
    side.scrollTop = keepScroll;
  };
})(window.ET);
