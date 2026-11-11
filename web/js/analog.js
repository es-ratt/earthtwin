/* Moon Analog / Mars Analog flow (Google Earth style):
 *   1. Globe screen: the target body (Moon or Mars) on the left, a slowly rotating Earth on the right,
 *      and one search bar in the header. Clicking the empty bar lists every location; typing filters it.
 *   2. Choosing a location zooms into the globes, fades, and opens the result screen.
 *   3. Result screen: no search bar; the target body with the chosen target pinned, the Earth with pins 1–5 for
 *      the Top 5 analogs (real latitude/longitude). A Back button returns to the globe screen.
 * App wiring (routes, state, panel) stays in app.js; this file only draws and reports choices. */
(function (ET) {
  "use strict";

  var A = ET.Analog = {};
  var TEXTURES = {
    moon: "img/globe/moon_lroc_wac_lola_2048.jpg",          // LROC WAC global mosaic, south cap from USGS LOLA relief
    mars: "img/fallback/mars_trek_mdim21_eq.jpg",           // Viking MDIM 2.1 colour mosaic (NASA Mars Trek)
    earth: "img/globe/earth_bluemarble_2048.jpg"           // NASA Blue Marble Next Generation (GIBS)
  };
  var LOOKS = {
    moon: { atmo: null, limb: 0.35 },
    mars: { atmo: "rgba(255,140,90,0.45)", limb: 0.35 },
    earth: { atmo: "rgba(110,175,255,0.55)", limb: 0.3 }
  };
  var ZOOM_MS = 1300, REDUCED_MS = 150;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var data, cb, intro, result, tex = {}, ready = null, introBody = null, resultKey = "";

  function load(name) { return ET.Globe.loadTexture(TEXTURES[name]).then(function (t) { tex[name] = t; }); }
  A.ready = function (body) { return Promise.all([load(body), load("earth")]); };

  /* ------------------------------------------------------------ globe screen */
  /** Wide screens: side by side. Tall (phone) screens: target body upper left, Earth lower right. */
  function introLayout(which) {
    return function (w, h) {
      var m = Math.min(w, h), tall = h > w * 1.15;
      if (tall) return which === "target" ? { x: 0.36 * w, y: 0.42 * h, r: 0.36 * w } : { x: 0.66 * w, y: 0.74 * h, r: 0.3 * w };
      return which === "target" ? { x: 0.3 * w, y: 0.56 * h, r: 0.34 * m } : { x: 0.69 * w, y: 0.54 * h, r: 0.25 * m };
    };
  }
  function resultLayout(which) {
    return function (w, h) {
      var r = Math.min(0.3 * Math.min(w, h), 0.23 * w);
      return { x: (which === "target" ? 0.25 : 0.75) * w, y: 0.55 * h, r: r };
    };
  }

  function introBodies(body) {
    return [
      { id: body, tex: tex[body], look: LOOKS[body], cx: 0.3, cy: 0.56, layout: introLayout("target"), tilt: body === "moon" ? -12 : 18,
        lon: body === "moon" ? 0 : -160, spin: body === "mars" ? 4 : 0, swing: body === "moon" ? 18 : 0 },
      { id: "earth", tex: tex.earth, look: LOOKS.earth, cx: 0.69, cy: 0.54, layout: introLayout("earth"), tilt: 18, lon: -40, spin: 7 }
    ];
  }

  A.showIntro = function (body) {
    var el = document.getElementById("analog-intro");
    el.classList.remove("zooming");
    el.hidden = false;
    if (result) result.stop();
    A.ready(body).then(function () {
      if (!intro) intro = new ET.Globe.Scene(document.getElementById("intro-globe"), { reduceMotion: reduceMotion });
      if (introBody !== body) { intro.setBodies(introBodies(body)); introBody = body; }
      intro.start();
    }).catch(showError);
  };

  A.hideIntro = function () {
    document.getElementById("analog-intro").hidden = true;
    if (intro) intro.stop();
  };

  /** Zoom into the globe that holds the chosen location, fade, then call done(). */
  A.playZoom = function (towards, done) {
    var el = document.getElementById("analog-intro");
    var b = intro && intro.bodies.find(function (x) { return x.id === towards; });
    var L = b && intro._layout(b);
    el.style.transformOrigin = L ? (L.x / intro.w * 100) + "% " + (L.y / intro.h * 100) + "%" : "50% 50%";
    el.style.setProperty("--zoom-ms", (reduceMotion ? REDUCED_MS : ZOOM_MS) + "ms");
    void el.offsetWidth;                                              // restart the CSS transition
    el.classList.add("zooming");
    setTimeout(done, reduceMotion ? REDUCED_MS : ZOOM_MS * 0.85);
  };

  /* ------------------------------------------------------------ result screen */
  function rankPins(siteRes, selectedId) {
    var top = siteRes.candidates.filter(function (e) { return e.group === "analog"; });
    var pins = top.map(function (e) {
      var c = data.candById[e.id];
      return { id: e.id, lat: c.lat, lon: c.lon, label: String(e.rank), kind: "rank", title: e.rank + ". " + c.name + " · similarity " + e.score_pct + "%" };
    });
    if (selectedId && !pins.some(function (p) { return p.id === selectedId; })) {
      var e = siteRes.candidates.find(function (x) { return x.id === selectedId; }), c = data.candById[selectedId];
      if (e && c) pins.push({ id: c.id, lat: c.lat, lon: c.lon, label: e.rank ? String(e.rank) : "–", kind: "rank",
        title: c.name + (e.score_pct !== null ? " · similarity " + e.score_pct + "%" : " · not scored") });
    }
    return pins;
  }

  /** Pins near both poles cannot face the camera at once: the Earth then rocks slowly between them. */
  function bothPoles(pins) { return pins.some(function (p) { return p.lat > 45; }) && pins.some(function (p) { return p.lat < -45; }); }

  function meanLat(pins) {
    if (!pins.length || bothPoles(pins)) return 0;
    var s = pins.reduce(function (a, p) { return a + p.lat; }, 0) / pins.length;
    return Math.max(-35, Math.min(35, s * 0.5));
  }

  /** Draw (or update) the result globes for a mission/target; pins follow the Top 5 for that target only. */
  A.showResult = function (mission, site, siteRes, candidateId) {
    var body = mission.body;
    document.getElementById("globe-pane").hidden = false;
    A.ready(body).then(function () {
      if (!result) {
        result = new ET.Globe.Scene(document.getElementById("result-globe"), {
          reduceMotion: reduceMotion, tip: document.getElementById("globe-tip"),
          onPin: function (id) { if (id !== "target" && cb.selectCandidate) cb.selectCandidate(id); }
        });
      }
      var key = mission.id + "/" + site.id;
      var pos = site.position || {};
      var hasPos = pos.lat !== null && pos.lat !== undefined;
      var pins = rankPins(siteRes, candidateId);
      if (key !== resultKey || pins.length !== (result.bodies[1] || { pins: [] }).pins.length) {
        var targetPins = hasPos ? [{ id: "target", lat: pos.lat, lon: pos.lon, label: "★", kind: "target", title: site.name + " (chosen target)" }] : [];
        result.setBodies([
          { id: body, tex: tex[body], look: LOOKS[body], cx: 0.25, cy: 0.55, layout: resultLayout("target"), tilt: hasPos ? pos.lat * 0.8 : 0, lon: hasPos ? pos.lon : 0,
            swing: 0, pins: targetPins },
          { id: "earth", tex: tex.earth, look: LOOKS.earth, cx: 0.75, cy: 0.55, layout: resultLayout("earth"), tilt: meanLat(pins), tiltHome: meanLat(pins), tiltSwing: bothPoles(pins) ? 40 : 0,
            lon: 0, spin: 6, pins: pins }
        ]);
        if (hasPos) result.face(body, pos.lat, pos.lon, 0.8);
        resultKey = key;
      } else {
        result.bodies[1].pins = pins;
      }
      document.getElementById("globe-note").textContent = hasPos ? "" : "No position for " + site.name + " in the sources yet, so it has no pin.";
      A.selectPin(candidateId);
      result.start();
    }).catch(showError);
  };

  /** Highlight a pin and turn the Earth so it faces the camera (or release the Earth to spin again). */
  A.selectPin = function (id) {
    if (!result) return;
    result.select(id || null);
    var p = id && (result.bodies[1] || { pins: [] }).pins.find(function (x) { return x.id === id; });
    if (p) result.face("earth", p.lat, p.lon, 0.75); else result.release("earth");
  };

  /** On-screen pins of the result globes (CSS px inside the globe canvas), for tests and accessibility tooling. */
  A.pinPositions = function () {
    return result ? result.pinHits.map(function (h) { return { id: h.pin.id, label: h.pin.label, x: Math.round(h.x), y: Math.round(h.y), z: +h.z.toFixed(2) }; }) : [];
  };

  A.hideResult = function () {
    document.getElementById("globe-pane").hidden = true;
    if (result) result.stop();
  };

  function showError(err) {
    var note = document.getElementById("globe-note");
    if (note) note.textContent = "Globe textures could not be loaded (" + err.message + "). Use the Map view.";
  }

  /* ------------------------------------------------------------ header search */
  var input, list, wrap, items = [], active = -1, body = "moon";

  function locations() {
    var mission = data.missions.find(function (m) { return m.in_selector && m.body === body; });
    var targets = mission.target_site_ids.concat(mission.reference_site_ids || []).map(function (id) {
      var s = data.sitesById[id];
      var ref = (mission.reference_site_ids || []).indexOf(id) >= 0 ? "reference site" : s.role.replace(/_/g, " ");
      return { kind: "target", id: id, name: s.name, sub: (body === "moon" ? "Moon" : "Mars") + " target · " + ref };
    });
    var earth = data.earth.map(function (c) { return { kind: "earth", id: c.id, name: c.name, sub: "Earth site · " + c.country }; });
    return { targets: targets, earth: earth };
  }

  function render(q) {
    var all = locations(), needle = (q || "").trim().toLowerCase();
    function match(x) { return !needle || (x.name + " " + x.sub).toLowerCase().indexOf(needle) >= 0; }
    var groups = [[body === "moon" ? "Moon targets · Artemis IV" : "Mars targets · SkyFall", all.targets.filter(match)], ["Earth sites", all.earth.filter(match)]];
    items = [];
    var html = groups.map(function (g) {
      if (!g[1].length) return "";
      return '<li class="search-group" role="presentation">' + ET.esc(g[0]) + "</li>" + g[1].map(function (x) {
        var i = items.push(x) - 1;
        return '<li class="search-item" role="option" id="search-opt-' + i + '" data-i="' + i + '" aria-selected="false">' +
          '<span class="search-dot ' + x.kind + '"></span><span><span class="search-name">' + ET.esc(x.name) + '</span><span class="search-sub">' + ET.esc(x.sub) + "</span></span></li>";
      }).join("");
    }).join("");
    list.innerHTML = html || '<li class="search-empty" role="presentation">No location matches “' + ET.esc(q) + "”.</li>";
    setActive(items.length ? 0 : -1);
  }

  function open() { render(input.value); list.hidden = false; input.setAttribute("aria-expanded", "true"); wrap.classList.add("open"); }
  function close() { list.hidden = true; input.setAttribute("aria-expanded", "false"); wrap.classList.remove("open"); setActive(-1); }

  function setActive(i) {
    active = i;
    list.querySelectorAll(".search-item").forEach(function (li) {
      var on = Number(li.dataset.i) === i;
      li.classList.toggle("active", on); li.setAttribute("aria-selected", on ? "true" : "false");
      if (on) li.scrollIntoView({ block: "nearest" });
    });
    if (i >= 0) input.setAttribute("aria-activedescendant", "search-opt-" + i); else input.removeAttribute("aria-activedescendant");
  }

  function choose(i) {
    var x = items[i];
    if (!x) return;
    close(); input.value = ""; input.blur();
    cb.choose(x);
  }

  A.initSearch = function () {
    wrap = document.getElementById("nav-search"); input = document.getElementById("search-input"); list = document.getElementById("search-list");
    input.addEventListener("focus", open);
    input.addEventListener("click", function () { if (list.hidden) open(); });
    input.addEventListener("input", function () { render(input.value); if (list.hidden) open(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); if (list.hidden) open(); else setActive(Math.min(items.length - 1, active + 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive(Math.max(0, active - 1)); }
      else if (e.key === "Enter") { e.preventDefault(); if (active >= 0) choose(active); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); input.blur(); }
    });
    list.addEventListener("mousedown", function (e) { e.preventDefault(); });   // keep focus while clicking
    list.addEventListener("click", function (e) { var li = e.target.closest(".search-item"); if (li) choose(Number(li.dataset.i)); });
    list.addEventListener("mousemove", function (e) { var li = e.target.closest(".search-item"); if (li && Number(li.dataset.i) !== active) setActive(Number(li.dataset.i)); });
    document.addEventListener("click", function (e) { if (!wrap.contains(e.target)) close(); });
  };

  /** Show the search bar for one world (on the globe screen only). */
  A.setSearch = function (visible, world) {
    body = world || body;
    wrap.hidden = !visible;
    input.placeholder = "Search " + (body === "moon" ? "Moon targets" : "Mars targets") + " or Earth sites";
    if (!visible) close();
  };

  /** @param d app data  @param callbacks { choose(item), selectCandidate(id) } */
  A.init = function (d, callbacks) { data = d; cb = callbacks; A.initSearch(); };
})(window.ET);
