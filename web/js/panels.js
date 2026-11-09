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
  function missionBlock(mission, data) {
    var when = mission.when ? esc(mission.when.value) : "";
    return '<div class="sec">' +
      '<span class="label">' + esc(mission.agency) + " · " + esc(mission.kind) + "</span>" +
      '<div class="mission-name">' + esc(mission.name) + "</div>" +
      '<div class="mission-meta">' + when + (mission.when ? " " + ET.statusBadge(mission.when.status) : "") + "</div>" +
      '<p class="muted" style="margin:10px 0 0;font-size:13px">' + esc(mission.summary) + "</p>" +
      (mission.banner ? '<div class="notice">' + esc(mission.banner) + "</div>" : "") +
      "</div>";
  }

  function siteBlock(mission, site, siteRes, data) {
    var opts = mission.target_site_ids.concat(mission.reference_site_ids || []).map(function (id) {
      var s = data.sitesById[id];
      var ref = (mission.reference_site_ids || []).indexOf(id) >= 0 ? " (reference, not a mission region)" : "";
      return '<option value="' + esc(id) + '"' + (id === site.id ? " selected" : "") + ">" + esc(s.name + ref) + "</option>";
    }).join("");
    var cov = siteRes.target_coverage;
    var flags = (site.flags || []).map(function (f) { return '<span class="badge">' + esc(f.replace(/_/g, " ")) + "</span>"; }).join("");
    var facts = (site.facts || []).map(function (f) {
      var fl = (f.flags || []).map(function (x) { return '<span class="badge' + (x === "inconsistent_in_docs" ? " verify" : "") + '">' + esc(x.replace(/_/g, " ")) + "</span>"; }).join(" ");
      return '<div class="fact"><span class="k">' + esc(f.label) + "</span>" + esc(f.text) +
        (f.note ? ' <span class="muted">— ' + esc(f.note) + "</span>" : "") +
        '<div class="src">' + (f.source_id ? srcLink(f.source_id, data) : "No source") + (fl ? " " + fl : "") + "</div></div>";
    }).join("");
    return '<div class="sec">' +
      '<label class="label" for="site-select">Target site · ' + (mission.body === "moon" ? "Moon" : "Mars") + "</label>" +
      '<select class="site" id="site-select">' + opts + "</select>" +
      '<div class="site-meta">' + ET.statusBadge(site.status) + " " + '<span class="badge">' + esc(site.role.replace(/_/g, " ")) + "</span>" + flags + "</div>" +
      '<div class="coverage" data-tip="Share of the scoring weight for which this target site has a value in the team documents. Features without data are left out, never guessed.">Target data coverage <b class="num" style="color:#e9ecef">' + ET.pct(cov) + '</b><div class="meter"><i style="width:' + Math.round(cov * 100) + '%"></i></div></div>' +
      (facts ? '<details class="facts" style="margin-top:14px"><summary class="label">Site facts from team documents (' + site.facts.length + ")</summary>" + facts + "</details>" : "") +
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
  function noteTip(m) {
    var n = m && m.note;
    return n ? ' data-tip="' + esc(n) + '"' : "";
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
    var res = data.results[state.missionId];
    var siteRes = res.sites[state.siteId];
    var html = missionBlock(mission, data);
    if (res.contains_sample) {
      var used = res.method.features;
      var sample = {}, measured = {};
      data.earth.forEach(function (c) {
        used.forEach(function (f) {
          var m = c.features[f];
          if (!m) return;
          if (m.status === "SAMPLE") sample[f] = 1;
          if (m.status === "measured") measured[f] = 1;
        });
      });
      var lab = function (o) { return Object.keys(o).map(function (f) { return data.fdefs[f].label; }).join(", "); };
      html += '<div class="sample-strip" data-tip="' + esc(ET.GLOSSARY.SAMPLE) + '"><b>Still SAMPLE on the Earth side:</b> ' + esc(lab(sample)) +
        ". " + (Object.keys(measured).length ? "<b>Measured from NASA data:</b> " + esc(lab(measured)) + ". " : "") +
        "Rankings are not final results until the SAMPLE values are replaced.</div>";
    }
    html += siteBlock(mission, site, siteRes, data);
    var entry = state.candidateId && siteRes.candidates.find(function (e) { return e.id === state.candidateId; });
    html += entry ? detailBlock(entry, siteRes, data) : listBlock(siteRes, state, data);
    var side = document.getElementById("side");
    var keepScroll = entry ? 0 : side.scrollTop;
    side.innerHTML = html;
    side.scrollTop = keepScroll;
  };
})(window.ET);
