/* Google-Earth-style globes on a plain 2D canvas (no library: the site's CSP allows only its own scripts).
 *
 *   ET.Globe.loadTexture(url)       → Promise<{w, h, data}>  equirectangular image, −180…180° longitude
 *   new ET.Globe.Body(tex, look)    a textured sphere that can be tilted (view latitude) and turned (view longitude)
 *   new ET.Globe.Scene(canvas, opts) draws stars, bodies and numbered pins; hover/click on pins; eases the view
 *
 * Rendering: for each pixel of the disc we precompute its latitude/longitude for the current tilt, so turning
 * the globe is only a texture offset per frame. The table is rebuilt only when the size or the tilt changes. */
(function (ET) {
  "use strict";

  var G = ET.Globe = {};
  var DEG = Math.PI / 180;
  var TILT_EPS = 0.15;                         // rebuild the lookup table when the tilt moves more than this (deg)
  var PIN_R = 13;                              // numbered pin radius (CSS px)
  var EASE = 2.6;                              // view easing speed (per second)
  var MAX_DPR = 1.25;                          // globes are per-pixel work: keep the backing store modest

  var cache = {};
  G.loadTexture = function (url) {
    if (cache[url]) return cache[url];
    cache[url] = new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () {
        var c = document.createElement("canvas");
        c.width = img.naturalWidth; c.height = img.naturalHeight;
        var g = c.getContext("2d");
        g.drawImage(img, 0, 0);
        resolve({ w: c.width, h: c.height, data: g.getImageData(0, 0, c.width, c.height).data });
      };
      img.onerror = function () { reject(new Error("texture failed to load: " + url)); };
      img.src = url;
    });
    return cache[url];
  };

  /* ------------------------------------------------------------ one sphere */
  /** look: { atmo: "rgba(...)" | null, limb: 0..1 (edge darkening) } */
  G.Body = function (tex, look) {
    this.tex = tex; this.look = look || {};
    this.r = 0; this.tilt = null; this.canvas = document.createElement("canvas"); this.ctx = this.canvas.getContext("2d");
  };

  G.Body.prototype.build = function (rPx, tiltDeg) {
    var r = Math.max(4, Math.round(rPx)), size = r * 2, t = this.tex;
    this.r = r; this.tilt = tiltDeg;
    this.canvas.width = this.canvas.height = size;
    this.img = this.ctx.createImageData(size, size);
    var n = size * size, u0 = new Float32Array(n), v = new Int32Array(n), shade = new Float32Array(n), alpha = new Uint8ClampedArray(n), idx = [];
    var c = Math.cos(tiltDeg * DEG), s = Math.sin(tiltDeg * DEG), limb = this.look.limb === undefined ? 0.3 : this.look.limb;
    for (var y = 0; y < size; y++) for (var x = 0; x < size; x++) {
      var nx = (x + 0.5 - r) / r, ny = (y + 0.5 - r) / r, d2 = nx * nx + ny * ny;
      if (d2 > 1) continue;
      var z = Math.sqrt(1 - d2), up = -ny, i = y * size + x;
      var yb = up * c + z * s, zb = -up * s + z * c;                 // view → body (rotate about the screen x axis)
      u0[i] = (Math.atan2(nx, zb) / (2 * Math.PI)) * t.w;
      v[i] = Math.min(t.h - 1, Math.max(0, Math.floor((0.5 - Math.asin(Math.max(-1, Math.min(1, yb))) / Math.PI) * t.h)));
      shade[i] = (1 - limb) + limb * Math.pow(z, 0.6);
      alpha[i] = Math.min(255, (1 - Math.sqrt(d2)) * r * 1.6 * 255);
      idx.push(i);
    }
    this.u0 = u0; this.v = v; this.shade = shade; this.alpha = alpha; this.idx = idx;
  };

  /** Draw with the given view centre longitude (deg). Returns the sphere canvas (2r × 2r device px). */
  G.Body.prototype.render = function (lonDeg) {
    var t = this.tex, tw = t.w, td = t.data, px = this.img.data, off = ((lonDeg + 180) / 360) * tw;
    var u0 = this.u0, v = this.v, sh = this.shade, al = this.alpha, idx = this.idx;
    for (var k = 0; k < idx.length; k++) {
      var i = idx[k], u = (u0[i] + off) | 0;
      u %= tw; if (u < 0) u += tw;
      var p = (v[i] * tw + u) * 4, o = i * 4, f = sh[i];
      px[o] = td[p] * f; px[o + 1] = td[p + 1] * f; px[o + 2] = td[p + 2] * f; px[o + 3] = al[i];
    }
    this.ctx.putImageData(this.img, 0, 0);
    return this.canvas;
  };

  /** Screen offset (in units of r) of a lat/lon for view (tiltDeg, lonDeg); z > 0 = on the visible face. */
  G.project = function (lat, lon, tiltDeg, lonDeg) {
    var la = lat * DEG, dl = (lon - lonDeg) * DEG, c = Math.cos(tiltDeg * DEG), s = Math.sin(tiltDeg * DEG);
    var xb = Math.cos(la) * Math.sin(dl), yb = Math.sin(la), zb = Math.cos(la) * Math.cos(dl);
    return { x: xb, y: -(yb * c - zb * s), z: yb * s + zb * c };
  };

  function shortestAngle(from, to) { var d = ((to - from) % 360 + 540) % 360 - 180; return from + d; }

  /* ------------------------------------------------------------ scene */
  /**
   * opts: { onPin(id), onHover(pin|null), tip: HTMLElement, reduceMotion }
   * bodies: [{ id, tex, look, cx, cy, r (fractions of canvas w/h/min), tilt, lon, spin (deg/s), pins: [...] }]
   * pin: { id, lat, lon, label, title, kind: "rank" | "target" }
   */
  G.Scene = function (canvas, opts) {
    this.canvas = canvas; this.ctx = canvas.getContext("2d"); this.opts = opts || {};
    this.bodies = []; this.stars = []; this.selected = null; this.hover = null;
    this.running = false; this.raf = 0; this.last = 0; this.pinHits = [];
    var self = this;
    canvas.addEventListener("pointermove", function (e) { self._pointer(e, false); });
    canvas.addEventListener("pointerleave", function () { self._setHover(null); });
    canvas.addEventListener("click", function (e) { self._pointer(e, true); });
    window.addEventListener("resize", function () { if (self.running) self.resize(); });
    document.addEventListener("visibilitychange", function () { if (document.hidden) self._pause(); else if (self.running) self._loop(); });
  };

  G.Scene.prototype.setBodies = function (bodies) {
    this.bodies = bodies.map(function (b) {
      return Object.assign({ view: { tilt: b.tilt || 0, lon: b.lon || 0 }, goal: null, body: new G.Body(b.tex, b.look) }, b);
    });
    this.resize();
  };

  G.Scene.prototype.resize = function () {
    var rect = this.canvas.getBoundingClientRect();
    this.w = Math.max(1, rect.width); this.h = Math.max(1, rect.height);
    this.dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
    this.canvas.width = Math.round(this.w * this.dpr); this.canvas.height = Math.round(this.h * this.dpr);
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    var rnd = ET.Art.rng(911), n = Math.round(this.w * this.h / 3500);
    this.stars = [];
    for (var i = 0; i < n; i++) this.stars.push({ x: rnd() * this.w, y: rnd() * this.h, r: 0.3 + Math.pow(rnd(), 4) * 1.3, a: 0.25 + rnd() * 0.6, tw: rnd() * 6 });
    this.bodies.forEach(function (b) { b.body.tilt = null; });
    this.draw(0);
  };

  /** Turn a body so a lat/lon faces the camera (eased); spin stops while a goal is set. */
  G.Scene.prototype.face = function (bodyId, lat, lon, tiltFactor) {
    var b = this.bodies.find(function (x) { return x.id === bodyId; });
    if (!b) return;
    b.goal = { tilt: Math.max(-70, Math.min(70, lat * (tiltFactor === undefined ? 0.75 : tiltFactor))), lon: shortestAngle(b.view.lon, lon) };
  };
  G.Scene.prototype.release = function (bodyId) {
    var b = this.bodies.find(function (x) { return x.id === bodyId; });
    if (b) b.goal = null;
  };
  G.Scene.prototype.select = function (pinId) { this.selected = pinId; if (!this.running) this.draw(0); };

  G.Scene.prototype.start = function () { if (this.running) return; this.running = true; this.resize(); this._loop(); };
  G.Scene.prototype.stop = function () { this.running = false; this._pause(); this._setHover(null); };
  G.Scene.prototype._pause = function () { cancelAnimationFrame(this.raf); this.raf = 0; };
  G.Scene.prototype._loop = function () {
    var self = this;
    if (this.raf || document.hidden) return;
    this.last = 0;
    var tick = function (ts) {
      if (!self.running) { self.raf = 0; return; }
      self.raf = requestAnimationFrame(tick);
      var dt = self.last ? Math.min(0.1, (ts - self.last) / 1000) : 0;
      self.last = ts;
      self.draw(dt);
    };
    this.raf = requestAnimationFrame(tick);
  };

  G.Scene.prototype._layout = function (b) {
    if (b.layout) return b.layout(this.w, this.h);                  // body-specific layout (adapts to tall screens)
    var m = Math.min(this.w, this.h);
    return { x: b.cx * this.w, y: b.cy * this.h, r: b.r * m };
  };

  G.Scene.prototype.draw = function (dt) {
    var g = this.ctx, w = this.w, h = this.h, rm = this.opts.reduceMotion;
    g.fillStyle = "#070a12"; g.fillRect(0, 0, w, h);
    var tnow = performance.now() / 1000;
    for (var i = 0; i < this.stars.length; i++) {
      var s = this.stars[i], a = rm ? s.a : s.a * (0.7 + 0.3 * Math.sin(tnow * 0.8 + s.tw));
      g.fillStyle = "rgba(255,255,255," + a.toFixed(2) + ")"; g.fillRect(s.x, s.y, s.r * 1.4, s.r * 1.4);
    }
    var hits = [];
    var self = this;
    this.bodies.forEach(function (b) {
      if (b.goal) {
        var k = rm ? 1 : Math.min(1, dt * EASE);
        b.view.tilt += (b.goal.tilt - b.view.tilt) * k; b.view.lon += (b.goal.lon - b.view.lon) * k;
      } else if (!rm) {
        b.view.lon += (b.spin || 0) * dt;
        if (b.swing) b.view.lon = b.lon + b.swing * Math.sin(tnow * 0.12);
        if (b.tiltHome !== undefined) {                                  // tiltSwing rocks north ↔ south so polar pins on both sides show
          var home = b.tiltHome + (b.tiltSwing || 0) * Math.sin(tnow * 0.16);
          b.view.tilt += (home - b.view.tilt) * Math.min(1, dt * 0.8);
        }
      }
      var L = self._layout(b), rDev = L.r * self.dpr;
      if (b.body.r !== Math.round(rDev) || b.body.tilt === null || Math.abs(b.body.tilt - b.view.tilt) > TILT_EPS) b.body.build(rDev, b.view.tilt);
      self._halo(L, b.look);
      g.drawImage(b.body.render(b.view.lon), L.x - L.r, L.y - L.r, L.r * 2, L.r * 2);
      self._rim(L, b.look);
      (b.pins || []).forEach(function (p) {
        var q = G.project(p.lat, p.lon, b.body.tilt, b.view.lon);
        if (q.z < 0.04) return;                                         // far side: appears as the globe turns
        hits.push({ pin: p, x: L.x + q.x * L.r, y: L.y + q.y * L.r, z: q.z });
      });
    });
    declutter(hits);
    hits.sort(function (a, b) { return a.z - b.z; }).forEach(function (hp) { self._pin(hp); });
    this.pinHits = hits;
    if (this.hover) this._placeTip();
  };

  /** Pins closer than one pin width (e.g. Beacon Valley and McMurdo, ~25 km apart) are fanned out around their
   * true spot; a short leader line and dot keep the exact position visible. */
  function declutter(hits) {
    var used = [];
    hits.forEach(function (h) { h.ax = h.x; h.ay = h.y; });
    hits.forEach(function (h, i) {
      if (used[i]) return;
      var group = [h];
      for (var j = i + 1; j < hits.length; j++) if (!used[j] && Math.hypot(hits[j].x - h.x, hits[j].y - h.y) < PIN_R * 2) { group.push(hits[j]); used[j] = true; }
      if (group.length < 2) return;
      var cx = group.reduce(function (s, g) { return s + g.x; }, 0) / group.length, cy = group.reduce(function (s, g) { return s + g.y; }, 0) / group.length;
      var rad = PIN_R * (group.length > 2 ? 1.9 : 1.4);
      group.forEach(function (g, k) {
        var ang = -Math.PI / 2 + (k - (group.length - 1) / 2) * (Math.PI / 2.2);
        g.x = cx + rad * Math.cos(ang) * 1.4; g.y = cy + rad * Math.sin(ang);
        g.fanned = true;
      });
    });
  }

  G.Scene.prototype._halo = function (L, look) {
    if (!look || !look.atmo) return;
    var g = this.ctx, grad = g.createRadialGradient(L.x, L.y, L.r * 0.95, L.x, L.y, L.r * 1.25);
    grad.addColorStop(0, look.atmo); grad.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = grad; g.beginPath(); g.arc(L.x, L.y, L.r * 1.25, 0, Math.PI * 2); g.fill();
  };
  G.Scene.prototype._rim = function (L, look) {
    if (!look || !look.atmo) return;
    var g = this.ctx, grad = g.createRadialGradient(L.x, L.y, 0, L.x, L.y, L.r);
    grad.addColorStop(0, "rgba(0,0,0,0)"); grad.addColorStop(0.86, "rgba(0,0,0,0)"); grad.addColorStop(1, look.atmo);
    g.fillStyle = grad; g.beginPath(); g.arc(L.x, L.y, L.r, 0, Math.PI * 2); g.fill();
  };

  G.Scene.prototype._pin = function (hp) {
    var g = this.ctx, p = hp.pin, on = this.selected === p.id || (this.hover && this.hover.pin.id === p.id);
    var r = PIN_R * (on ? 1.18 : 1), fade = Math.min(1, hp.z / 0.25);
    g.save(); g.globalAlpha = 0.35 + 0.65 * fade;
    if (hp.fanned) {                                                    // leader line to the exact position
      g.strokeStyle = "rgba(255,255,255,0.85)"; g.lineWidth = 1.2;
      g.beginPath(); g.moveTo(hp.ax, hp.ay); g.lineTo(hp.x, hp.y); g.stroke();
      g.fillStyle = "#fff"; g.beginPath(); g.arc(hp.ax, hp.ay, 2.2, 0, Math.PI * 2); g.fill();
    }
    g.shadowColor = "rgba(0,0,0,0.6)"; g.shadowBlur = 6; g.shadowOffsetY = 1;
    g.fillStyle = p.kind === "target" ? "#ffd166" : on ? "#5cc8ff" : "#ffffff";
    g.beginPath(); g.arc(hp.x, hp.y, r, 0, Math.PI * 2); g.fill();
    g.shadowColor = "transparent";
    g.lineWidth = 2; g.strokeStyle = p.kind === "target" ? "#7a5200" : "#0b2540";
    g.stroke();
    g.fillStyle = "#06121f"; g.font = "600 " + Math.round(r * 1.05) + "px Sora, Inter, system-ui, sans-serif";
    g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(p.label, hp.x, hp.y + 0.5);
    g.restore();
  };

  G.Scene.prototype._pointer = function (e, click) {
    var rect = this.canvas.getBoundingClientRect(), x = e.clientX - rect.left, y = e.clientY - rect.top, best = null;
    this.pinHits.forEach(function (hp) { var d = Math.hypot(hp.x - x, hp.y - y); if (d <= PIN_R + 6 && (!best || d < best.d)) best = { hp: hp, d: d }; });
    this._setHover(best ? best.hp : null);
    if (click && best && this.opts.onPin) this.opts.onPin(best.hp.pin.id);
  };
  G.Scene.prototype._setHover = function (hp) {
    this.hover = hp;
    this.canvas.style.cursor = hp ? "pointer" : "default";
    var tip = this.opts.tip;
    if (!tip) return;
    tip.hidden = !hp;
    if (hp) { tip.textContent = hp.pin.title; this._placeTip(); }
  };
  G.Scene.prototype._placeTip = function () {
    var tip = this.opts.tip, hp = this.hover;
    if (!tip || !hp) return;
    var fresh = this.pinHits.find(function (x) { return x.pin.id === hp.pin.id; });
    if (!fresh) { tip.hidden = true; return; }
    tip.style.transform = "translate(" + Math.round(fresh.x + PIN_R + 8) + "px," + Math.round(fresh.y - 12) + "px)";
  };
})(window.ET);
