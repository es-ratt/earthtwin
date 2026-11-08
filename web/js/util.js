/* Shared helpers. Everything lives on window.ET so plain <script> tags work without a build step. */
window.ET = window.ET || {};

(function (ET) {
  "use strict";

  /** Escape text before putting it into HTML. Use for EVERY data value. */
  ET.esc = function (v) {
    if (v === null || v === undefined) return "";
    return String(v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  };

  ET.pct = function (x) { return x === null || x === undefined ? "—" : Math.round(x * 100) + "%"; };

  ET.ordinal = function (n) {
    var s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  };

  ET.dots = function (level) {
    var n = { high: 3, medium: 2, low: 1 }[level] || 0;
    var out = "";
    for (var i = 0; i < 3; i++) out += i < n ? "●" : '<span class="off">●</span>';
    return '<span class="dots" aria-label="confidence ' + ET.esc(level) + '">' + out + "</span>";
  };

  /** One-line plain-language explanations. Wrap jargon with ET.term("PSR"). */
  ET.GLOSSARY = {
    "PSR": "Permanently shadowed region: crater floors near the lunar poles that never see the Sun. They can trap water ice.",
    "HLS": "Human Landing System: the lander that takes Artemis astronauts from lunar orbit to the surface.",
    "GPR": "Ground-penetrating radar: sends radio waves into the ground to find layers and buried ice.",
    "LDA": "Lobate debris apron: a tongue-shaped slope deposit on Mars, often a glacier hidden under rock debris.",
    "LOLA": "Lunar Orbiter Laser Altimeter on NASA's LRO: measures the Moon's height and slopes.",
    "LRO": "Lunar Reconnaissance Orbiter: NASA spacecraft mapping the Moon since 2009.",
    "Diviner": "LRO's thermometer instrument: maps lunar surface temperatures.",
    "MOLA": "Mars Orbiter Laser Altimeter: the standard Mars elevation map.",
    "SHARAD": "Shallow radar on NASA's Mars Reconnaissance Orbiter: sees buried ice tens of metres deep.",
    "HiRISE": "High-resolution camera on Mars Reconnaissance Orbiter (~30 cm per pixel).",
    "regolith": "Loose broken rock and dust covering the surface.",
    "anorthosite": "A pale rock made mostly of plagioclase feldspar; the main rock of the lunar highlands.",
    "thermal inertia": "How slowly ground heats up and cools down. Firm or rocky ground has high thermal inertia; fine dust has low.",
    "permafrost": "Ground that stays frozen for at least two years in a row.",
    "proxy": "An indirect estimate used because the real measurement is not available.",
    "renormalised": "When a feature has no data it is left out and the other weights are scaled up so they still add to 100%.",
    "SAMPLE": "Placeholder value typed in so the app works. Not data. Replace before drawing conclusions.",
    "VERIFY": "Taken from the team documents but not yet checked against the original source.",
    "TODO": "Not found in the team documents. Left empty on purpose: nothing is guessed.",
    "Similarity Score": "How close an Earth place is to the target site on the chosen features, from 0% to 100%. It is not accuracy: there is no ground truth for the Moon or Mars.",
    "hard filter": "A mission limit that a place must pass to be ranked at all (e.g. slope under 15°).",
    "sensitivity": "How much the ranking changes if each category weight moves up or down by 10 percentage points."
  };

  ET.term = function (key, label) {
    var tip = ET.GLOSSARY[key];
    var text = ET.esc(label || key);
    return tip ? '<span data-tip="' + ET.esc(tip) + '">' + text + "</span>" : text;
  };

  /** Status badge for a value (SAMPLE / VERIFY / TODO / derived / method). */
  ET.statusBadge = function (status) {
    if (!status) return "";
    var s = String(status);
    var cls = s === "SAMPLE" ? "sample" : s === "verify" ? "verify" : s === "TODO" ? "todo" : "";
    var key = s === "verify" ? "VERIFY" : s;
    var tip = ET.GLOSSARY[key] || (s === "derived" ? "Calculated by the pipeline from other values." : s === "method" ? "Set by the EarthTwin method, not measured." : "");
    return '<span class="badge ' + cls + '"' + (tip ? ' data-tip="' + ET.esc(tip) + '"' : "") + ">" + ET.esc(key) + "</span>";
  };

  /* ---- tooltip (one element, follows the pointer; also works with keyboard focus) ---- */
  ET.initTooltips = function () {
    var tip = document.getElementById("tip");
    function show(el, x, y) {
      tip.textContent = el.getAttribute("data-tip");
      tip.classList.add("on");
      var w = tip.offsetWidth, h = tip.offsetHeight;
      var left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 12));
      var top = y + 16 + h > window.innerHeight ? y - h - 10 : y + 16;
      tip.style.left = left + "px";
      tip.style.top = top + "px";
    }
    document.addEventListener("mouseover", function (e) {
      var el = e.target.closest && e.target.closest("[data-tip]");
      if (el) show(el, e.clientX, e.clientY);
    });
    document.addEventListener("mousemove", function (e) {
      if (tip.classList.contains("on") && e.target.closest && e.target.closest("[data-tip]")) show(e.target.closest("[data-tip]"), e.clientX, e.clientY);
    });
    document.addEventListener("mouseout", function (e) {
      if (e.target.closest && e.target.closest("[data-tip]")) tip.classList.remove("on");
    });
    document.addEventListener("focusin", function (e) {
      var el = e.target.closest && e.target.closest("[data-tip]");
      if (el) { var r = el.getBoundingClientRect(); show(el, r.left, r.bottom); }
    });
    document.addEventListener("focusout", function () { tip.classList.remove("on"); });
  };

  ET.fetchJSON = function (url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(url + " → HTTP " + r.status);
      return r.json();
    });
  };
})(window.ET);
