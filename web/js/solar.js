/* Home page: a live, procedurally drawn solar system (Canvas 2D, no images).
 * Sun, Earth, Moon and Mars are highlighted; the other planets are dim background.
 * Clicking (or tapping) the Moon or Mars calls the onOpen(route) callback. */
(function (ET) {
  "use strict";

  var S = ET.Solar = {};

  var STAR_COUNT = 340;
  var HOVER_SPEED = 0.2;          // animation speed while the pointer is over the Moon or Mars
  var REDUCED_SPEED = 0.12;       // prefers-reduced-motion: slow everything right down
  var SPEED_EASE = 4;             // how fast the speed eases towards its target (per second)
  var MIN_HIT_PX = 24;            // generous invisible hit radius for small moving bodies
  var DIM_ALPHA = 0.45;           // background planets
  var TAU = Math.PI * 2;

  /* Orbit times are visual targets in seconds, not real periods. */
  var PLANETS = [
    { id: "mercury", period: 12, size: 2.6, colors: ["#d6d3cf", "#8a8580", "#4a4643"] },
    { id: "venus", period: 22, size: 3.8, colors: ["#fff3c4", "#e2c77a", "#8e7337"] },
    { id: "earth", period: 40, size: 11, hi: true, label: "EARTH", glow: "rgba(90,170,255,0.55)" },
    { id: "mars", period: 70, size: 9.5, hi: true, label: "MARS", glow: "rgba(255,110,60,0.55)", route: "mars-analog" },
    { id: "jupiter", period: 140, size: 7.5, bands: true, colors: ["#f1dcb8", "#c9a67a", "#7d5c3a"] },
    { id: "saturn", period: 200, size: 6.5, ring: true, colors: ["#f6e7b8", "#d8bf7d", "#8a733e"] },
    { id: "uranus", period: 280, size: 5, colors: ["#d4fbff", "#7fd8e6", "#2f8a9a"] },
    { id: "neptune", period: 360, size: 5, colors: ["#8fb2ff", "#3d66d6", "#162d7a"] }
  ];
  var MOON = { id: "moon", period: 6, size: 4.6, hi: true, label: "MOON", route: "moon-analog" };

  var canvas, ctx, tipEl, onOpen;
  var w = 0, h = 0, dpr = 1, unit = 1, topInset = 0;
  var stars = [], phases = {};
  var running = false, rafId = 0, lastTs = 0, simT = 0, speed = 1, targetSpeed = 1, realT = 0;
  var hoverId = null, positions = {};
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ------------------------------------------------------------ setup */
  function seededRandom(seed) {
    var s = seed;
    return function () { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
  }

  function makeStars() {
    var rnd = seededRandom(20261114);
    stars = [];
    for (var i = 0; i < STAR_COUNT; i++) {
      stars.push({
        x: rnd(), y: rnd(), r: 0.35 + rnd() * 1.05, base: 0.25 + rnd() * 0.6,
        tw: 0.15 + rnd() * 0.5, ph: rnd() * TAU, vx: (rnd() - 0.5) * 0.0016, vy: (rnd() - 0.5) * 0.0010
      });
    }
    PLANETS.concat([MOON]).forEach(function (p) { phases[p.id] = rnd() * TAU; });
  }

  function resize() {
    var rect = canvas.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = Math.max(1, rect.width); h = Math.max(1, rect.height);
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    topInset = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--header-h")) || 64;
    unit = Math.max(0.55, Math.min(1.5, Math.min(w, h - topInset) / 820));
  }

  /* Evenly spaced circular orbits that always fit the window. */
  function orbitRadius(i) {
    var maxR = Math.min(w, h - topInset) / 2 - 22 * unit;     // stay clear of the nav bar
    var r0 = 62 * unit;
    return r0 + i * (maxR - r0) / (PLANETS.length - 1);
  }

  /* ------------------------------------------------------------ drawing */
  function drawStars(dt) {
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      s.x = (s.x + s.vx * dt + 1) % 1;
      s.y = (s.y + s.vy * dt + 1) % 1;
      var a = s.base * (0.65 + 0.35 * Math.sin(realT * s.tw + s.ph));
      ctx.fillStyle = "rgba(255,255,255," + a.toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(s.x * w, s.y * h, s.r, 0, TAU); ctx.fill();
    }
  }

  function glow(x, y, r, color, scale) {
    var g = ctx.createRadialGradient(x, y, r * 0.6, x, y, r * scale);
    g.addColorStop(0, color); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r * scale, 0, TAU); ctx.fill();
  }

  function sphere(x, y, r, colors) {
    var g = ctx.createRadialGradient(x - r * 0.4, y - r * 0.4, r * 0.1, x, y, r);
    g.addColorStop(0, colors[0]); g.addColorStop(0.55, colors[1]); g.addColorStop(1, colors[2]);
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill();
  }

  function drawSun(cx, cy) {
    var r = 30 * unit;
    var pulse = 1 + 0.03 * Math.sin(realT * 0.8);
    glow(cx, cy, r, "rgba(255,150,40,0.35)", 3.4 * pulse);
    glow(cx, cy, r, "rgba(255,190,90,0.55)", 1.8);
    var g = ctx.createRadialGradient(cx - r * 0.25, cy - r * 0.25, r * 0.1, cx, cy, r);
    g.addColorStop(0, "#fff6d6"); g.addColorStop(0.45, "#ffc24a"); g.addColorStop(1, "#ff7a1a");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, r, 0, TAU); ctx.fill();
    label("SUN", cx, cy + r + 16 * unit, 1);
  }

  function drawEarth(x, y, r, bright) {
    glow(x, y, r, "rgba(90,170,255," + (0.45 + 0.25 * bright) + ")", 2.6);
    sphere(x, y, r, ["#9fd4ff", "#2f7fe0", "#0b2f6e"]);
    ctx.save(); ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.clip();
    ctx.fillStyle = "rgba(70,150,90,0.85)";                       // land
    ctx.beginPath(); ctx.ellipse(x - r * 0.25, y - r * 0.1, r * 0.35, r * 0.5, 0.5, 0, TAU); ctx.fill();
    ctx.beginPath(); ctx.ellipse(x + r * 0.45, y + r * 0.25, r * 0.25, r * 0.3, -0.4, 0, TAU); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,0.8)";                      // clouds
    ctx.beginPath(); ctx.ellipse(x + r * 0.1, y - r * 0.55, r * 0.6, r * 0.12, 0.2, 0, TAU); ctx.fill();
    ctx.beginPath(); ctx.ellipse(x - r * 0.3, y + r * 0.55, r * 0.45, r * 0.1, -0.2, 0, TAU); ctx.fill();
    ctx.restore();
  }

  function drawMars(x, y, r, bright) {
    glow(x, y, r, "rgba(255,110,60," + (0.4 + 0.35 * bright) + ")", 2.6 + bright * 0.6);
    sphere(x, y, r, bright ? ["#ffc29a", "#f06a35", "#7a2410"] : ["#ffb08a", "#d9572a", "#6b200e"]);
    ctx.save(); ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.clip();
    ctx.fillStyle = "rgba(110,35,15,0.45)";
    ctx.beginPath(); ctx.ellipse(x + r * 0.2, y + r * 0.1, r * 0.5, r * 0.15, 0.3, 0, TAU); ctx.fill();
    ctx.fillStyle = "rgba(255,245,235,0.8)";                      // polar cap
    ctx.beginPath(); ctx.ellipse(x, y - r * 0.92, r * 0.42, r * 0.16, 0, 0, TAU); ctx.fill();
    ctx.restore();
  }

  function drawMoon(x, y, r, bright) {
    glow(x, y, r, "rgba(230,230,240," + (0.35 + 0.4 * bright) + ")", 2.8 + bright);
    sphere(x, y, r, bright ? ["#ffffff", "#d8d8dc", "#7c7c84"] : ["#f2f2f2", "#b8b8bd", "#5f5f66"]);
    ctx.fillStyle = "rgba(90,90,98,0.45)";
    ctx.beginPath(); ctx.arc(x + r * 0.25, y + r * 0.1, r * 0.25, 0, TAU); ctx.fill();
  }

  function drawBackgroundPlanet(p, x, y, r) {
    ctx.save(); ctx.globalAlpha = DIM_ALPHA;
    if (p.ring) {
      ctx.strokeStyle = "rgba(230,210,150,0.8)"; ctx.lineWidth = Math.max(1, r * 0.22);
      ctx.beginPath(); ctx.ellipse(x, y, r * 2, r * 0.7, -0.35, 0, TAU); ctx.stroke();
    }
    sphere(x, y, r, p.colors);
    if (p.bands) {
      ctx.save(); ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.clip();
      ctx.fillStyle = "rgba(120,80,45,0.5)";
      [-0.45, -0.1, 0.3].forEach(function (k, i) { ctx.fillRect(x - r, y + k * r, r * 2, r * (i === 1 ? 0.18 : 0.12)); });
      ctx.restore();
    }
    ctx.restore();
  }

  function label(text, x, y, alpha) {
    ctx.font = "500 " + Math.round(11 * Math.max(unit, 0.9)) + "px Inter, system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(255,255,255," + alpha + ")";
    var spaced = text.split("").join(String.fromCharCode(8202));   // hair spaces: wide letter spacing
    ctx.fillText(spaced, x, y);
  }

  function drawOrbit(cx, cy, r, alpha) {
    ctx.strokeStyle = "rgba(255,255,255," + alpha + ")"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, TAU); ctx.stroke();
  }

  function frame(cx, cy) {
    PLANETS.forEach(function (p, i) { drawOrbit(cx, cy, orbitRadius(i), p.hi ? 0.16 : 0.07); });
    drawSun(cx, cy);
    positions = {};
    PLANETS.forEach(function (p, i) {
      var a = phases[p.id] + TAU * simT / p.period;
      var R = orbitRadius(i), r = p.size * unit;
      var x = cx + R * Math.cos(a), y = cy + R * Math.sin(a);
      positions[p.id] = { x: x, y: y, r: r };
      if (!p.hi) { drawBackgroundPlanet(p, x, y, r); return; }
      if (p.id === "earth") {
        drawEarth(x, y, r, 0);
        label(p.label, x, y + r + 14 * unit, 0.85);
        var mr = 20 * unit + r;                                   // Moon orbit, always near Earth
        drawOrbit(x, y, mr, 0.14);
        var ma = phases.moon + TAU * simT / MOON.period;
        var mx = x + mr * Math.cos(ma), my = y + mr * Math.sin(ma);
        var mrad = MOON.size * unit;
        positions.moon = { x: mx, y: my, r: mrad };
        drawMoon(mx, my, mrad, hoverId === "moon" ? 1 : 0);
        var off = mrad + 14 * unit;                                // label on the side facing away from Earth
        label(MOON.label, mx + Math.cos(ma) * off * 1.6, my + Math.sin(ma) * off, hoverId === "moon" ? 1 : 0.8);
      } else if (p.id === "mars") {
        drawMars(x, y, r, hoverId === "mars" ? 1 : 0);
        label(p.label, x, y + r + 14 * unit, hoverId === "mars" ? 1 : 0.85);
      }
    });
  }

  /* ------------------------------------------------------------ loop */
  function tick(ts) {
    if (!running) return;
    var dt = lastTs ? Math.min(0.1, (ts - lastTs) / 1000) : 0;
    lastTs = ts;
    var base = reduceMotion ? REDUCED_SPEED : 1;
    var goal = (hoverId ? HOVER_SPEED : 1) * base;
    targetSpeed = goal;
    speed += (targetSpeed - speed) * Math.min(1, dt * SPEED_EASE);
    simT += dt * speed;
    realT += dt * (reduceMotion ? REDUCED_SPEED : 1);
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, w, h);
    drawStars(dt * (reduceMotion ? REDUCED_SPEED : 1));
    frame(w / 2, topInset + (h - topInset) / 2);
    if (hoverId) placeTip();
    rafId = requestAnimationFrame(tick);
  }

  /* ------------------------------------------------------------ interaction */
  function hitTest(px, py) {
    var best = null;
    ["moon", "mars"].forEach(function (id) {
      var p = positions[id];
      if (!p) return;
      var d = Math.hypot(px - p.x, py - p.y);
      var hitR = Math.max(MIN_HIT_PX, p.r + 10);
      if (d <= hitR && (!best || d < best.d)) best = { id: id, d: d };
    });
    return best ? best.id : null;
  }

  function localPoint(e) {
    var rect = canvas.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  }

  function placeTip() {
    var p = positions[hoverId];
    if (!p || !tipEl) return;
    tipEl.style.transform = "translate(" + Math.round(p.x + p.r + 14) + "px," + Math.round(p.y - 12) + "px)";
  }

  function setHover(id, showTip) {
    if (!canvas || !tipEl) return;
    hoverId = id;
    canvas.style.cursor = id ? "pointer" : "default";
    tipEl.hidden = !(id && showTip);
    if (id) placeTip();
  }

  function routeFor(id) { return id === "moon" ? MOON.route : id === "mars" ? "mars-analog" : null; }

  function bindPointer() {
    canvas.addEventListener("pointermove", function (e) {
      if (e.pointerType === "touch") return;
      var pt = localPoint(e);
      setHover(hitTest(pt[0], pt[1]), true);
    });
    canvas.addEventListener("pointerleave", function () { setHover(null, false); });
    canvas.addEventListener("pointerup", function (e) {
      var pt = localPoint(e);
      var id = hitTest(pt[0], pt[1]);
      if (id && onOpen) { setHover(null, false); onOpen(routeFor(id)); }
    });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) pause(); else if (S.active) resume();
    });
    window.addEventListener("resize", function () { if (canvas) resize(); });
  }

  function pause() { running = false; cancelAnimationFrame(rafId); }
  function resume() {
    if (running || !canvas) return;
    resize(); running = true; lastTs = 0; rafId = requestAnimationFrame(tick);
  }

  /* ------------------------------------------------------------ public */
  S.active = false;

  /** @param {HTMLCanvasElement} el  @param {HTMLElement} tip  @param {(route: string) => void} open */
  S.init = function (el, tip, open) {
    canvas = el; tipEl = tip; onOpen = open;
    ctx = canvas.getContext("2d");
    if (!ctx) return;
    makeStars(); resize(); bindPointer();
  };

  /** Current on-screen position of a body (CSS px within the canvas), for tests and accessibility tooling. */
  S.bodyPosition = function (id) { var p = positions[id]; return p ? { x: p.x, y: p.y, r: p.r } : null; };

  S.start = function () { S.active = true; if (!document.hidden) resume(); };
  S.stop = function () { S.active = false; setHover(null, false); pause(); };
})(window.ET);
