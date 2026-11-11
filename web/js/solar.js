/* Home hero: a cinematic, live solar system (Canvas 2D, procedural, no image files).
 *
 * Four focus bodies are large, sharp and lit: the Sun (boiling plasma, flares, corona) at the far left,
 * Earth (oceans, continents, drifting clouds, blue rim), the Moon (cratered, on a steady circular loop around
 * Earth) and Mars (rust surface, dust haze, thin glowing atmosphere). Mercury, Venus, Jupiter, Saturn, Uranus,
 * Neptune and an asteroid belt are tiny, dim and soft. A teal/purple nebula drifts, stars twinkle, a comet
 * crosses the upper right now and then. The camera pushes in slowly and eases back (a seamless loop).
 *
 * No text is drawn inside the animation. Clicking the Moon or Mars calls onOpen(route).
 * Performance: capped at 60 fps, paused when the tab is hidden, lighter on weak devices.
 * prefers-reduced-motion: one still frame, no push-in, no comets.
 * Public API (unchanged): ET.Solar.init(canvas, tip, onOpen), start(), stop(), active, bodyPosition(id). */
(function (ET) {
  "use strict";

  var S = ET.Solar = {};
  var A = ET.Art;
  var TAU = Math.PI * 2;

  var FRAME_MS = 1000 / 60 - 1;      // 60 fps cap
  var LOOP_S = 48;                   // camera push-in period (eases in and back out: no cut)
  var PUSH = 0.065;                  // maximum extra zoom of the push-in
  var PARALLAX_PX = 14;              // mouse parallax at full depth
  var HOVER_SPEED = 0.2;             // time slows while the pointer is on the Moon or Mars
  var SPEED_EASE = 4;
  var MIN_HIT_PX = 26;
  var ORBIT_TILT = -0.08;            // radians, whole system
  var ORBIT_RATIO = 0.36;            // ellipse b/a: a wide-angle, slightly-from-above view
  var COMET_GAP = [9, 17];           // seconds between comets

  /* Background planets: small, dim, soft. Orbit radius as a multiple of Earth's (inner) or Mars' (outer) orbit.
   * Spacing is compressed (an artistic view, not to scale) so every orbit crosses the frame. */
  var BACK = [
    { id: "mercury", k: 0.62, ref: "earth", size: 1.6, period: 70, colors: ["#d9d4cf", "#8f8984", "#4a4643"], glow: "rgba(220,210,200,0.25)" },
    { id: "venus", k: 0.8, ref: "earth", size: 2.4, period: 95, colors: ["#fff1c8", "#e2c77a", "#8e7337"], glow: "rgba(255,230,170,0.3)" },
    { id: "jupiter", k: 1.12, ref: "mars", size: 4.4, period: 160, bands: true, colors: ["#f1dcb8", "#c9a67a", "#7d5c3a"], glow: "rgba(240,210,170,0.25)" },
    { id: "saturn", k: 1.24, ref: "mars", size: 3.6, period: 210, ring: true, colors: ["#f6e7b8", "#d8bf7d", "#8a733e"], glow: "rgba(246,231,184,0.25)" },
    { id: "uranus", k: 1.36, ref: "mars", size: 2.6, period: 260, colors: ["#d4fbff", "#7fd8e6", "#2f8a9a"], glow: "rgba(150,230,240,0.25)" },
    { id: "neptune", k: 1.48, ref: "mars", size: 2.6, period: 320, colors: ["#8fb2ff", "#3d66d6", "#162d7a"], glow: "rgba(110,150,255,0.25)" }
  ];

  var canvas, ctx, tipEl, onOpen;
  var w = 0, h = 0, dpr = 1, topInset = 0, low = false;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var running = false, rafId = 0, lastTs = 0, lastDraw = 0, simT = 0, realT = 0, speed = 1;
  var hoverId = null, positions = {}, backPos = {};
  var mouse = { x: 0, y: 0, tx: 0, ty: 0 };
  var L = null;                      // layout (recomputed on resize)
  var art = null;                    // generated textures and spheres
  var stars = [], belt = [], comets = [], nextComet = 6, flares = [];

  /* ------------------------------------------------------------ layout */
  function orbitPoint(o, ang) {
    var x = o.a * Math.cos(ang), y = o.b * Math.sin(ang);
    var c = Math.cos(ORBIT_TILT), s = Math.sin(ORBIT_TILT);
    return { x: L.sun.x + x * c - y * s, y: L.sun.y + x * s + y * c };
  }

  /** Ellipse (centred on the Sun) that passes through screen point p; returns {a, b, ang}. */
  function orbitThrough(px, py) {
    var c = Math.cos(-ORBIT_TILT), s = Math.sin(-ORBIT_TILT);
    var dx = (px - L.sun.x) * c - (py - L.sun.y) * s, dy = (px - L.sun.x) * s + (py - L.sun.y) * c;
    var ang = Math.atan2(dy / ORBIT_RATIO, dx), a = Math.hypot(dx, dy / ORBIT_RATIO);
    return { a: a, b: a * ORBIT_RATIO, ang: ang };
  }

  function layout() {
    var portrait = h > w * 1.1, usable = h - topInset;
    var unit = portrait ? Math.min(w * 1.2, usable) : Math.min(usable, w * 0.62);
    L = { unit: unit, portrait: portrait };
    L.sun = portrait ? { x: -0.34 * w, y: topInset + usable * 0.3, r: 0.62 * w } : { x: -0.2 * usable, y: topInset + usable * 0.55, r: 0.62 * usable };
    var earthAt = portrait ? [0.5 * w, topInset + usable * 0.5] : [0.5 * w, topInset + usable * 0.6];
    var marsAt = portrait ? [0.72 * w, topInset + usable * 0.8] : [0.8 * w, topInset + usable * 0.32];
    L.earth = orbitThrough(earthAt[0], earthAt[1]); L.earth.r = unit * (portrait ? 0.1 : 0.105);
    L.mars = orbitThrough(marsAt[0], marsAt[1]); L.mars.r = unit * (portrait ? 0.075 : 0.078);
    L.moon = { r: unit * 0.03, orbit: L.earth.r * 2.15, period: 26 };
    L.focal = { x: 0.6 * w, y: topInset + usable * 0.5 };
    L.back = BACK.map(function (p, i) {
      var ref = L[p.ref], o = { a: ref.a * p.k, b: ref.a * p.k * ORBIT_RATIO };
      return { def: p, a: o.a, b: o.b, ang: visibleAngle(o, i), r: Math.max(1.4, p.size * unit / 340) };
    });
    var m = L.mars;
    L.belt = { a0: m.a * 1.03, a1: m.a * 1.09 };
  }

  /** An angle on orbit o whose point is on screen and clear of the focus bodies (deterministic per planet). */
  function visibleAngle(o, idx) {
    var rnd = A.rng(4242 + idx * 97), best = null, sunEdge = L.sun.x + L.sun.r * 1.12, near = null, nearD = Infinity;
    for (var n = 0; n < 600; n++) {
      var ang = rnd() * TAU, p = orbitPoint(o, ang);
      var out = Math.max(0, w * 0.97 - p.x < 0 ? p.x - w * 0.97 : 0, topInset + 16 - p.y, p.y - (h - 30));
      if (p.x > sunEdge && out < nearD) { nearD = out; near = ang; }   // fallback: the least off-screen point
      if (p.x < Math.max(sunEdge, w * 0.2) || p.x > w * 0.985 || p.y < topInset + 16 || p.y > h - 30) continue;
      if (Math.hypot(p.x - L.sun.x, p.y - L.sun.y) < L.sun.r * 1.15) continue;
      var e = orbitPoint(L.earth, L.earth.ang), mm = orbitPoint(L.mars, L.mars.ang);
      if (Math.hypot(p.x - e.x, p.y - e.y) < L.earth.r * 3 || Math.hypot(p.x - mm.x, p.y - mm.y) < L.mars.r * 2.5) continue;
      best = ang; break;
    }
    return best !== null ? best : near !== null ? near : 0.3;
  }

  /* ------------------------------------------------------------ assets */
  function buildArt() {
    var sdpr = low ? 1 : dpr;
    var lightFrom = function (body) {                     // direction from body to the Sun, slightly towards the viewer
      var p = orbitPoint(body, body.ang);
      return [L.sun.x - p.x, L.sun.y - p.y, Math.hypot(L.sun.x - p.x, L.sun.y - p.y) * 0.45];
    };
    var texW = low ? 256 : 512, texH = texW / 2;
    if (!art || art.texW !== texW) {
      art = { texW: texW };
      art.earthTex = A.texture("earth", texW, texH, 21);
      art.cloudTex = A.texture("clouds", texW, texH, 22);
      art.marsTex = A.texture("mars", texW, texH, 23);
      art.hazeTex = A.texture("haze", texW, texH, 24);
      art.moonTex = A.texture("moon", texW / 2, texH / 2, 25);
      art.plasma = A.plasma(low ? 128 : 192, 3);
      art.nebula = A.nebula(low ? 160 : 260, low ? 90 : 150, 11);
    }
    art.earth = new A.Sphere(L.earth.r * sdpr, art.earthTex, art.cloudTex, lightFrom(L.earth));
    art.mars = new A.Sphere(L.mars.r * sdpr, art.marsTex, art.hazeTex, lightFrom(L.mars));
    art.moon = new A.Sphere(L.moon.r * sdpr, art.moonTex, null, lightFrom(L.earth));
    art.sprites = {};
    L.back.forEach(function (b) { art.sprites[b.def.id] = A.planetSprite(b.def, b.r * dpr, low ? 0 : 0.8 * dpr); });
  }

  function makeParticles() {
    var rnd = A.rng(20261114), n = low ? 170 : 340;
    stars = [];
    for (var i = 0; i < n; i++) stars.push({ x: rnd(), y: rnd(), r: 0.3 + Math.pow(rnd(), 3) * 1.4, base: 0.25 + rnd() * 0.6, tw: 0.3 + rnd() * 1.2, ph: rnd() * TAU, hue: rnd() });
    belt = [];
    for (i = 0; i < (low ? 180 : 420); i++) belt.push({ t: rnd(), ang: rnd() * TAU, jit: (rnd() - 0.5) * 0.04, r: 0.4 + rnd() * 0.8, a: 0.15 + rnd() * 0.3, w: 0.004 + rnd() * 0.004 });
    flares = [];
    for (i = 0; i < 5; i++) flares.push({ ang: -0.95 + i * 0.45 + rnd() * 0.15, period: 7 + rnd() * 6, phase: rnd() * 10, size: 0.03 + rnd() * 0.035 });
  }

  /* ------------------------------------------------------------ camera */
  function camera() {
    var push = reduceMotion ? 0 : PUSH * (1 - Math.cos(TAU * realT / LOOP_S)) / 2;
    return { zoom: 1 + push, px: mouse.x * PARALLAX_PX, py: mouse.y * PARALLAX_PX };
  }
  function view(cam, depth, x, y) {
    var z = 1 + (cam.zoom - 1) * depth;
    return { x: L.focal.x + (x - L.focal.x) * z + cam.px * depth, y: L.focal.y + (y - L.focal.y) * z + cam.py * depth, z: z };
  }

  /* ------------------------------------------------------------ drawing */
  function drawSpace(cam) {
    var g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "#060914"); g.addColorStop(1, "#090c18");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
    var shift = Math.sin(realT * 0.02) * 0.04;            // nebula drifts and breathes slowly
    var nb = view(cam, 0.08, w * (0.48 + shift), h * 0.42);
    ctx.save(); ctx.globalAlpha = 0.85 + 0.15 * Math.sin(realT * 0.05);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(art.nebula, nb.x - w * 0.62, nb.y - h * 0.62, w * 1.24, h * 1.24);
    ctx.restore();
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i], p = view(cam, 0.15, s.x * w, s.y * h);
      var a = s.base * (reduceMotion ? 1 : 0.6 + 0.4 * Math.sin(realT * s.tw + s.ph));
      ctx.fillStyle = s.hue > 0.85 ? "rgba(255,226,190," + a.toFixed(3) + ")" : s.hue < 0.15 ? "rgba(190,215,255," + a.toFixed(3) + ")" : "rgba(255,255,255," + a.toFixed(3) + ")";
      ctx.beginPath(); ctx.arc(p.x, p.y, s.r, 0, TAU); ctx.fill();
    }
  }

  function drawOrbit(o, cam, alpha) {
    ctx.strokeStyle = "rgba(255,255,255," + alpha + ")"; ctx.lineWidth = 1;
    ctx.beginPath();
    for (var i = 0; i <= 160; i++) {
      var p = orbitPoint(o, i / 160 * TAU), v = view(cam, 1, p.x, p.y);
      if (i === 0) ctx.moveTo(v.x, v.y); else ctx.lineTo(v.x, v.y);
    }
    ctx.stroke();
  }

  function drawSun(cam) {
    var c = view(cam, 1, L.sun.x, L.sun.y), r = L.sun.r * c.z, pulse = 1 + 0.035 * Math.sin(realT * 0.7);
    ctx.save(); ctx.globalCompositeOperation = "lighter";
    var halo = ctx.createRadialGradient(c.x, c.y, r * 0.9, c.x, c.y, r * 2.6 * pulse);
    halo.addColorStop(0, "rgba(255,150,50,0.34)"); halo.addColorStop(0.35, "rgba(255,110,40,0.12)"); halo.addColorStop(1, "rgba(255,90,20,0)");
    ctx.fillStyle = halo; ctx.fillRect(0, 0, w, h);
    for (var k = 0; k < 3; k++) {                          // soft light shafts: a volumetric feel
      var ang = -0.35 + k * 0.33 + Math.sin(realT * 0.03 + k) * 0.03;
      ctx.save(); ctx.translate(c.x, c.y); ctx.rotate(ang);
      var sh = ctx.createLinearGradient(r, 0, r * 4.2, 0);
      sh.addColorStop(0, "rgba(255,190,110,0.028)"); sh.addColorStop(1, "rgba(255,190,110,0)");
      ctx.fillStyle = sh; ctx.beginPath(); ctx.moveTo(r, -r * 0.12); ctx.lineTo(r * 4.2, -r * 0.5); ctx.lineTo(r * 4.2, r * 0.5); ctx.lineTo(r, r * 0.12); ctx.fill();
      ctx.restore();
    }
    ctx.restore();

    ctx.save(); ctx.beginPath(); ctx.arc(c.x, c.y, r, 0, TAU); ctx.clip();
    var pat = ctx.createPattern(art.plasma, "repeat"), scale = r / 260;
    [[0.6, 0.010, 1], [-0.45, 0.016, 0.45]].forEach(function (layer, i) {
      if (pat.setTransform && window.DOMMatrix) pat.setTransform(new DOMMatrix().translateSelf(c.x + realT * layer[0] * 6, c.y + realT * layer[1] * 60).scaleSelf(scale * (1 + i * 0.6)));
      ctx.globalAlpha = layer[2]; ctx.globalCompositeOperation = i ? "overlay" : "source-over";
      ctx.fillStyle = pat; ctx.fillRect(c.x - r, c.y - r, r * 2, r * 2);
    });
    ctx.globalAlpha = 1; ctx.globalCompositeOperation = "source-over";
    var limb = ctx.createRadialGradient(c.x, c.y, r * 0.55, c.x, c.y, r);   // limb darkening and a hot core
    limb.addColorStop(0, "rgba(255,236,180,0.18)"); limb.addColorStop(0.7, "rgba(255,150,40,0)"); limb.addColorStop(1, "rgba(150,40,0,0.6)");
    ctx.fillStyle = limb; ctx.fillRect(c.x - r, c.y - r, r * 2, r * 2);
    ctx.restore();

    ctx.save(); ctx.globalCompositeOperation = "lighter";
    var rim = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, r * 1.12);     // stops start at the limb, never inside the disc
    rim.addColorStop(0, "rgba(255,200,110,0)"); rim.addColorStop(0.86, "rgba(255,200,110,0)");
    rim.addColorStop(0.89, "rgba(255,200,110,0.5)"); rim.addColorStop(1, "rgba(255,140,40,0)");
    ctx.fillStyle = rim; ctx.beginPath(); ctx.arc(c.x, c.y, r * 1.12, 0, TAU); ctx.fill();
    flares.forEach(function (f) { drawFlare(c, r, f); });
    ctx.restore();
  }

  /** A prominence loop on the visible limb that rises and fades on its own cycle. */
  function drawFlare(c, r, f) {
    var life = ((realT + f.phase) % f.period) / f.period, a = Math.sin(life * Math.PI);
    if (a < 0.02) return;
    var ang = f.ang + Math.sin(realT * 0.05 + f.phase) * 0.04, span = 0.035, hgt = r * f.size * (0.6 + 0.4 * a);
    var p0 = { x: c.x + r * Math.cos(ang - span), y: c.y + r * Math.sin(ang - span) };
    var p1 = { x: c.x + r * Math.cos(ang + span), y: c.y + r * Math.sin(ang + span) };
    var cp = { x: c.x + (r + hgt * 2) * Math.cos(ang), y: c.y + (r + hgt * 2) * Math.sin(ang) };
    ctx.lineCap = "round";
    [[r * 0.05, 0.10], [r * 0.022, 0.28], [r * 0.008, 0.6]].forEach(function (s) {
      ctx.strokeStyle = "rgba(255,170,70," + (s[1] * a * 0.8).toFixed(3) + ")"; ctx.lineWidth = s[0] * 0.8;
      ctx.beginPath(); ctx.moveTo(p0.x, p0.y); ctx.quadraticCurveTo(cp.x, cp.y, p1.x, p1.y); ctx.stroke();
    });
  }

  function drawBelt(cam) {
    ctx.fillStyle = "rgba(220,205,185,1)";
    for (var i = 0; i < belt.length; i++) {
      var b = belt[i], a = L.belt.a0 + (L.belt.a1 - L.belt.a0) * b.t;
      var p = orbitPoint({ a: a, b: a * ORBIT_RATIO }, b.ang + simT * b.w + b.jit), v = view(cam, 1, p.x, p.y);
      if (v.x < -4 || v.x > w + 4 || v.y < -4 || v.y > h + 4) continue;
      ctx.globalAlpha = b.a; ctx.fillRect(v.x, v.y, b.r, b.r);
    }
    ctx.globalAlpha = 1;
  }

  function drawBackPlanets(cam) {
    L.back.forEach(function (b) {
      var ang = b.ang + 0.05 * Math.sin(TAU * simT / b.def.period), p = orbitPoint(b, ang), v = view(cam, 1, p.x, p.y);
      var sp = art.sprites[b.def.id], sw = sp.width / dpr * v.z, sh = sp.height / dpr * v.z;
      backPos[b.def.id] = { x: v.x, y: v.y, r: b.r * v.z };
      ctx.globalAlpha = 0.75; ctx.drawImage(sp, v.x - sw / 2, v.y - sh / 2, sw, sh); ctx.globalAlpha = 1;
    });
  }

  function glow(x, y, r, inner, color) {
    var g = ctx.createRadialGradient(x, y, r * inner, x, y, r * 2.4);
    g.addColorStop(0, color); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, r * 2.4, 0, TAU); ctx.fill();
  }

  /** Lit sphere + atmosphere rim + sun-side rim light. */
  function drawFocus(sphere, x, y, r, rot, overlayRot, atmo, hot) {
    ctx.save(); ctx.globalCompositeOperation = "lighter";
    glow(x, y, r, 0.9, atmo.glow.replace("A", String(hot ? atmo.glowA * 1.6 : atmo.glowA)));
    ctx.restore();
    ctx.drawImage(sphere.render(rot, overlayRot), x - r, y - r, r * 2, r * 2);
    var sx = L.sun.x - x, sy = L.sun.y - y, d = Math.hypot(sx, sy), ux = sx / d, uy = sy / d;
    ctx.save(); ctx.globalCompositeOperation = "lighter";
    var rim = ctx.createRadialGradient(x, y, 0, x, y, r * 1.14);              // thin atmosphere ring around the limb only
    rim.addColorStop(0, "rgba(0,0,0,0)"); rim.addColorStop(0.8, "rgba(0,0,0,0)");
    rim.addColorStop(0.875, atmo.rim); rim.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = rim; ctx.beginPath(); ctx.arc(x, y, r * 1.14, 0, TAU); ctx.fill();
    var lit = ctx.createLinearGradient(x + ux * r, y + uy * r, x - ux * r * 0.2, y - uy * r * 0.2);   // warm rim light on the sun side
    lit.addColorStop(0, "rgba(255,210,150,0.24)"); lit.addColorStop(0.3, "rgba(255,210,150,0)");
    ctx.fillStyle = lit; ctx.beginPath(); ctx.arc(x, y, r * 1.01, 0, TAU); ctx.fill();
    ctx.restore();
  }

  var EARTH_ATMO = { glow: "rgba(70,150,255,A)", glowA: 0.3, rim: "rgba(110,180,255,0.6)" };
  var MARS_ATMO = { glow: "rgba(255,120,70,A)", glowA: 0.28, rim: "rgba(255,170,120,0.55)" };
  var MOON_ATMO = { glow: "rgba(225,228,240,A)", glowA: 0.16, rim: "rgba(235,235,245,0.18)" };

  function drawFocusBodies(cam) {
    var e = L.earth, eAng = e.ang + 0.04 * Math.sin(TAU * simT / 90);       // slow drift along the orbit line
    var ep = orbitPoint(e, eAng), ev = view(cam, 1, ep.x, ep.y), er = e.r * ev.z;
    var m = L.mars, mAng = m.ang + 0.03 * Math.sin(TAU * simT / 120 + 1.3);
    var mp = orbitPoint(m, mAng), mv = view(cam, 1, mp.x, mp.y), mr = m.r * mv.z;
    var ma = TAU * simT / L.moon.period + 0.6, mo = L.moon.orbit * ev.z;     // steady circular loop around Earth
    var moonX = ev.x + mo * Math.cos(ma), moonY = ev.y + mo * Math.sin(ma), moonR = L.moon.r * ev.z;

    drawFocus(art.mars, mv.x, mv.y, mr, simT / 150, simT / 60, MARS_ATMO, hoverId === "mars");
    ctx.strokeStyle = "rgba(255,255,255,0.13)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(ev.x, ev.y, mo, 0, TAU); ctx.stroke();
    var behind = Math.sin(ma) < 0 && Math.abs(moonX - ev.x) < er;            // keep the Moon in front of Earth when they overlap
    if (behind) drawFocus(art.moon, moonX, moonY, moonR, 0, 0, MOON_ATMO, hoverId === "moon");
    drawFocus(art.earth, ev.x, ev.y, er, simT / 110, simT / 70, EARTH_ATMO, false);
    if (!behind) drawFocus(art.moon, moonX, moonY, moonR, 0, 0, MOON_ATMO, hoverId === "moon");
    positions = { earth: { x: ev.x, y: ev.y, r: er }, mars: { x: mv.x, y: mv.y, r: mr }, moon: { x: moonX, y: moonY, r: moonR } };
    Object.keys(backPos).forEach(function (k) { positions[k] = backPos[k]; });
  }

  function drawComets(dt) {
    if (reduceMotion) return;
    nextComet -= dt;
    if (nextComet <= 0) {
      var rnd = Math.random;
      comets.push({ x: w * (0.7 + rnd() * 0.32), y: topInset + h * (0.02 + rnd() * 0.18), ang: Math.PI * (0.83 + rnd() * 0.08), v: w * (0.22 + rnd() * 0.1), life: 0, max: 2.4 + rnd() });
      nextComet = COMET_GAP[0] + Math.random() * (COMET_GAP[1] - COMET_GAP[0]);
    }
    ctx.save(); ctx.globalCompositeOperation = "lighter";
    comets = comets.filter(function (c) {
      c.life += dt; c.x += Math.cos(c.ang) * c.v * dt; c.y += Math.sin(c.ang) * c.v * dt;
      var a = Math.sin(Math.min(1, c.life / c.max) * Math.PI), len = 140;
      var tx = c.x - Math.cos(c.ang) * len, ty = c.y - Math.sin(c.ang) * len;
      var g = ctx.createLinearGradient(c.x, c.y, tx, ty);
      g.addColorStop(0, "rgba(220,240,255," + (0.85 * a).toFixed(3) + ")"); g.addColorStop(1, "rgba(150,200,255,0)");
      ctx.strokeStyle = g; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.moveTo(c.x, c.y); ctx.lineTo(tx, ty); ctx.stroke();
      ctx.fillStyle = "rgba(255,255,255," + a.toFixed(3) + ")"; ctx.beginPath(); ctx.arc(c.x, c.y, 1.6, 0, TAU); ctx.fill();
      return c.life < c.max;
    });
    ctx.restore();
  }

  function draw(dt) {
    var cam = camera();
    drawSpace(cam);
    drawOrbit(L.back[0], cam, 0.07); drawOrbit(L.back[1], cam, 0.08);
    drawOrbit(L.earth, cam, 0.26); drawOrbit(L.mars, cam, 0.24);
    for (var i = 2; i < L.back.length; i++) drawOrbit(L.back[i], cam, 0.07);
    drawBelt(cam);
    drawBackPlanets(cam);
    drawSun(cam);
    drawComets(dt);
    drawFocusBodies(cam);
    if (hoverId) placeTip();
  }

  /* ------------------------------------------------------------ loop */
  function tick(ts) {
    if (!running) return;
    rafId = requestAnimationFrame(tick);
    if (lastDraw && ts - lastDraw < FRAME_MS) return;      // 60 fps cap on high-refresh screens
    var dt = lastTs ? Math.min(0.1, (ts - lastTs) / 1000) : 0;
    lastTs = ts; lastDraw = ts;
    speed += ((hoverId ? HOVER_SPEED : 1) - speed) * Math.min(1, dt * SPEED_EASE);
    simT += dt * speed; realT += dt;
    mouse.x += (mouse.tx - mouse.x) * Math.min(1, dt * 2); mouse.y += (mouse.ty - mouse.y) * Math.min(1, dt * 2);
    draw(dt);
  }

  function resize() {
    var rect = canvas.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, low ? 1.25 : 2);
    w = Math.max(1, rect.width); h = Math.max(1, rect.height);
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    topInset = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--header-h")) || 64;
    layout(); buildArt();
  }

  function stillFrame() { if (canvas && w) draw(0); }

  /* ------------------------------------------------------------ interaction */
  function hitTest(px, py) {
    var best = null;
    ["moon", "mars"].forEach(function (id) {
      var p = positions[id];
      if (!p) return;
      var d = Math.hypot(px - p.x, py - p.y), hitR = Math.max(MIN_HIT_PX, p.r + 10);
      if (d <= hitR && (!best || d < best.d)) best = { id: id, d: d };
    });
    return best ? best.id : null;
  }

  function localPoint(e) { var rect = canvas.getBoundingClientRect(); return [e.clientX - rect.left, e.clientY - rect.top]; }

  function placeTip() {
    var p = positions[hoverId];
    if (!p || !tipEl) return;
    tipEl.style.transform = "translate(" + Math.round(p.x + p.r + 14) + "px," + Math.round(p.y - 12) + "px)";
  }

  function setHover(id, showTip) {
    if (!canvas || !tipEl) return;
    var changed = id !== hoverId;
    hoverId = id;
    canvas.style.cursor = id ? "pointer" : "default";
    tipEl.hidden = !(id && showTip);
    if (id) placeTip();
    if (changed && reduceMotion) stillFrame();
  }

  function routeFor(id) { return id === "moon" ? "moon-analog" : id === "mars" ? "mars-analog" : null; }

  function bindPointer() {
    canvas.addEventListener("pointermove", function (e) {
      if (e.pointerType === "touch") return;
      var pt = localPoint(e);
      mouse.tx = (pt[0] / w - 0.5) * 2; mouse.ty = (pt[1] / h - 0.5) * 2;
      setHover(hitTest(pt[0], pt[1]), true);
    });
    canvas.addEventListener("pointerleave", function () { setHover(null, false); mouse.tx = mouse.ty = 0; });
    canvas.addEventListener("pointerup", function (e) {
      var pt = localPoint(e), id = hitTest(pt[0], pt[1]);
      if (id && onOpen) { setHover(null, false); onOpen(routeFor(id)); }
    });
    document.addEventListener("visibilitychange", function () { if (document.hidden) pause(); else if (S.active) resume(); });
    window.addEventListener("resize", function () { if (canvas && S.active) { resize(); if (reduceMotion) stillFrame(); } });
  }

  function pause() { running = false; cancelAnimationFrame(rafId); }
  function resume() {
    if (running || !canvas) return;
    resize();
    if (reduceMotion) { stillFrame(); return; }             // a still frame, no animation loop
    running = true; lastTs = 0; lastDraw = 0; rafId = requestAnimationFrame(tick);
  }

  function weakDevice() {
    var cores = navigator.hardwareConcurrency || 8, mem = navigator.deviceMemory || 8;
    return cores <= 4 || mem <= 4 || window.innerWidth * window.innerHeight < 480000;
  }

  /* ------------------------------------------------------------ public */
  S.active = false;

  /** @param {HTMLCanvasElement} el  @param {HTMLElement} tip  @param {(route: string) => void} open */
  S.init = function (el, tip, open) {
    canvas = el; tipEl = tip; onOpen = open;
    ctx = canvas.getContext("2d");
    if (!ctx || !A) return;
    low = weakDevice();
    makeParticles(); bindPointer();
  };

  /** Current on-screen position of a body (CSS px within the canvas), for tests and accessibility tooling. */
  S.bodyPosition = function (id) { var p = positions[id]; return p ? { x: p.x, y: p.y, r: p.r } : null; };

  S.start = function () { S.active = true; if (!document.hidden) resume(); };
  S.stop = function () { S.active = false; setHover(null, false); pause(); };
})(window.ET);
