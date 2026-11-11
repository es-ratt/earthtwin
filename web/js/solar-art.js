/* Procedural art shared by the home hero (solar.js) and the page backgrounds (backdrop.js).
 * Everything is generated in the browser from seeded noise: no image files, no licences to track.
 *
 *   ET.Art.rng(seed)                     seeded random 0..1
 *   ET.Art.noise(seed)                   value noise + fBm, optionally tileable in x
 *   ET.Art.canvas(w, h)                  offscreen canvas
 *   ET.Art.texture(kind, w, h)           equirectangular RGBA maps: earth, clouds, mars, haze, moon
 *   ET.Art.Sphere(r, tex, overlay, L)    textured, lit sphere renderer (precomputed lookup, fast per frame)
 *   ET.Art.plasma(size)                  tileable Sun surface texture
 *   ET.Art.nebula(w, h, seed)            teal-green + purple nebula
 *   ET.Art.planetSprite(def, r, blur)    small soft background planet (Saturn gets rings)
 */
(function (ET) {
  "use strict";

  var A = ET.Art = {};
  var TAU = Math.PI * 2;

  A.rng = function (seed) {
    var s = (seed % 2147483646) + 1;
    return function () { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
  };

  A.canvas = function (w, h) {
    var c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(w)); c.height = Math.max(1, Math.round(h));
    return c;
  };

  /* ------------------------------------------------------------ noise */
  /** Value noise on an integer lattice; `px` / `py` make it tile with that lattice period. */
  A.noise = function (seed) {
    var rnd = A.rng(seed), perm = new Uint16Array(512), vals = new Float32Array(256);
    for (var i = 0; i < 256; i++) { perm[i] = i; vals[i] = rnd(); }
    for (i = 255; i > 0; i--) { var j = Math.floor(rnd() * (i + 1)), t = perm[i]; perm[i] = perm[j]; perm[j] = t; }
    for (i = 0; i < 256; i++) perm[i + 256] = perm[i];
    function lat(x, y) { return vals[perm[(perm[x & 255] + y) & 511]]; }
    function smooth(t) { return t * t * (3 - 2 * t); }
    function wrap(i, p) { return p ? ((i % p) + p) % p : i; }
    function n2(x, y, px, py) {
      var xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
      var x0 = wrap(xi, px), x1 = wrap(xi + 1, px), y0 = wrap(yi, py), y1 = wrap(yi + 1, py);
      var u = smooth(xf), v = smooth(yf);
      var a = lat(x0, y0), b = lat(x1, y0), c = lat(x0, y1), d = lat(x1, y1);
      return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
    }
    function fbm(x, y, oct, px, py) {
      var sum = 0, amp = 0.5, f = 1, norm = 0;
      for (var o = 0; o < oct; o++) { sum += amp * n2(x * f, y * f, px ? px * f : 0, py ? py * f : 0); norm += amp; amp *= 0.5; f *= 2; }
      return sum / norm;
    }
    return { n2: n2, fbm: fbm };
  };

  function mix(a, b, t) { return a + (b - a) * t; }
  function clamp01(t) { return t < 0 ? 0 : t > 1 ? 1 : t; }
  function smoothstep(a, b, x) { var t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); }

  /* ------------------------------------------------------------ planet maps (equirectangular, tile in longitude) */
  var PAINTERS = {
    earth: function (nz, u, v, lat, out) {
      var land = nz.fbm(u * 6, v * 3, 5, 6), detail = nz.fbm(u * 24 + 7, v * 12, 3, 24);
      var ice = smoothstep(0.78, 0.9, Math.abs(lat) + (detail - 0.5) * 0.12);
      if (land > 0.505) {                                       // continents: green near the equator, brown in deserts
        var dry = nz.fbm(u * 4 + 31, v * 2, 3, 4), k = smoothstep(0.505, 0.7, land);
        var g = dry > 0.52 ? [150, 122, 76] : [64, 112, 58];
        out[0] = mix(g[0], 120, k * 0.4) * (0.8 + detail * 0.4); out[1] = mix(g[1], 98, k * 0.4) * (0.8 + detail * 0.4); out[2] = mix(g[2], 60, k * 0.4) * (0.8 + detail * 0.4);
      } else {                                                 // oceans: deep blue, lighter on shelves
        var shelf = smoothstep(0.42, 0.505, land);
        out[0] = mix(6, 30, shelf); out[1] = mix(34, 96, shelf); out[2] = mix(104, 170, shelf);
      }
      out[0] = mix(out[0], 236, ice); out[1] = mix(out[1], 242, ice); out[2] = mix(out[2], 248, ice); out[3] = 255;
    },
    clouds: function (nz, u, v, lat, out) {
      var c = nz.fbm(u * 8 + 50, v * 5, 5, 8), streak = nz.fbm(u * 3 + 90, v * 14, 3, 3);
      var a = smoothstep(0.58, 0.8, c * 0.75 + streak * 0.35);
      out[0] = out[1] = out[2] = 255; out[3] = a * 200;
    },
    mars: function (nz, u, v, lat, out) {
      var base = nz.fbm(u * 5, v * 3, 5, 5), dark = nz.fbm(u * 3 + 17, v * 2, 4, 3), fine = nz.fbm(u * 30, v * 16, 2, 30);
      var albedo = smoothstep(0.47, 0.62, dark);
      var r = mix(190, 92, albedo), g = mix(84, 36, albedo), b = mix(40, 22, albedo);
      var shade = 0.82 + base * 0.32 + (fine - 0.5) * 0.12;
      var cap = smoothstep(0.86, 0.93, Math.abs(lat) + (fine - 0.5) * 0.05);
      out[0] = mix(r * shade, 240, cap); out[1] = mix(g * shade, 232, cap); out[2] = mix(b * shade, 226, cap); out[3] = 255;
    },
    haze: function (nz, u, v, lat, out) {
      var h = nz.fbm(u * 5 + 70, v * 4, 4, 5);
      out[0] = 238; out[1] = 160; out[2] = 110; out[3] = smoothstep(0.55, 0.8, h) * 38;
    },
    moon: function (nz, u, v, lat, out) {
      var mare = smoothstep(0.55, 0.62, nz.fbm(u * 3 + 5, v * 2, 4, 3)), grain = nz.fbm(u * 40, v * 20, 3, 40);
      var hi = 168 + (grain - 0.5) * 50, lo = 92 + (grain - 0.5) * 30;
      out[0] = mix(hi + 4, lo, mare); out[1] = mix(hi + 2, lo + 2, mare); out[2] = mix(hi - 2, lo + 8, mare); out[3] = 255;
    }
  };

  /** Equirectangular texture as {w, h, data: Uint8ClampedArray}. */
  A.texture = function (kind, w, h, seed) {
    var nz = A.noise(seed || 7), data = new Uint8ClampedArray(w * h * 4), out = [0, 0, 0, 0], paint = PAINTERS[kind];
    for (var y = 0; y < h; y++) {
      var v = y / h, lat = 1 - 2 * v;                       // +1 north pole … −1 south pole (sin-free, good enough)
      for (var x = 0; x < w; x++) {
        paint(nz, x / w, v, lat, out);
        var i = (y * w + x) * 4;
        data[i] = out[0]; data[i + 1] = out[1]; data[i + 2] = out[2]; data[i + 3] = out[3];
      }
    }
    if (kind === "moon") craters(data, w, h, seed || 7);
    return { w: w, h: h, data: data };
  };

  function craters(data, w, h, seed) {
    var rnd = A.rng(seed + 99);
    for (var n = 0; n < 160; n++) {
      var cx = rnd() * w, cy = h * (0.12 + rnd() * 0.76), r = 1.5 + Math.pow(rnd(), 3) * 14;
      for (var dy = -r - 1; dy <= r + 1; dy++) for (var dx = -r - 1; dx <= r + 1; dx++) {
        var d = Math.sqrt(dx * dx + dy * dy) / r;
        if (d > 1.15) continue;
        var x = ((Math.round(cx + dx) % w) + w) % w, y = Math.round(cy + dy);
        if (y < 0 || y >= h) continue;
        var k = d < 0.85 ? -18 * (1 - d) : d < 1.05 ? 22 : 0;  // dark floor, bright rim
        var i = (y * w + x) * 4;
        data[i] += k; data[i + 1] += k; data[i + 2] += k;
      }
    }
  }

  /* ------------------------------------------------------------ textured sphere */
  /**
   * Precomputes, for every pixel of a disc of radius r (device px), the texture coordinates and the
   * Lambert shading for light direction L = [x, y, z] (screen space, z towards the viewer).
   * render(rot, overlayRot) then only does table look-ups: cheap enough for 60 fps.
   */
  A.Sphere = function (r, tex, overlay, L) {
    r = Math.max(4, Math.round(r));
    var size = r * 2, cv = A.canvas(size, size), cx = cv.getContext("2d");
    var img = cx.createImageData(size, size), n = size * size;
    var tu = new Float32Array(n), tv = new Int32Array(n), lit = new Float32Array(n), edge = new Float32Array(n), inside = [];
    var ll = Math.hypot(L[0], L[1], L[2]), lx = L[0] / ll, ly = L[1] / ll, lz = L[2] / ll;
    for (var y = 0; y < size; y++) for (var x = 0; x < size; x++) {
      var nx = (x + 0.5 - r) / r, ny = (y + 0.5 - r) / r, d2 = nx * nx + ny * ny;
      if (d2 > 1) continue;
      var nzv = Math.sqrt(1 - d2), i = y * size + x;
      tu[i] = (Math.atan2(nx, nzv) / TAU + 0.5) * tex.w;
      tv[i] = Math.min(tex.h - 1, Math.floor((0.5 + Math.asin(ny) / Math.PI) * tex.h));
      var lam = nx * lx + ny * ly + nzv * lz;
      lit[i] = 0.06 + 0.94 * Math.pow(clamp01(lam * 1.08 + 0.04), 0.85);
      edge[i] = clamp01((1 - Math.sqrt(d2)) * r * 1.4);          // 1-px anti-aliased rim
      inside.push(i);
    }
    var px = img.data, tw = tex.w, td = tex.data, ow = overlay ? overlay.w : 0, od = overlay ? overlay.data : null;
    this.radius = r;
    this.canvas = cv;
    this.render = function (rot, overlayRot) {
      var off = ((rot % 1) + 1) % 1 * tw, ooff = overlay ? ((overlayRot % 1) + 1) % 1 * ow : 0;
      for (var k = 0; k < inside.length; k++) {
        var i = inside[k], u = (tu[i] + off) | 0;
        if (u >= tw) u -= tw;
        var t = (tv[i] * tw + u) * 4, R = td[t], G = td[t + 1], B = td[t + 2];
        if (od) {
          var ou = ((tu[i] / tw) * ow + ooff) | 0;
          if (ou >= ow) ou -= ow;
          var o = (tv[i] * ow + ou) * 4, a = od[o + 3] / 255;
          R += (od[o] - R) * a; G += (od[o + 1] - G) * a; B += (od[o + 2] - B) * a;
        }
        var s = lit[i], p = i * 4;
        px[p] = R * s; px[p + 1] = G * s; px[p + 2] = B * s; px[p + 3] = 255 * edge[i];
      }
      cx.putImageData(img, 0, 0);
      return cv;
    };
  };

  /* ------------------------------------------------------------ Sun, nebula, sprites */
  /** Tileable orange-gold plasma (turbulent fBm) for the Sun's surface pattern. */
  A.plasma = function (size, seed) {
    var c = A.canvas(size, size), g = c.getContext("2d"), img = g.createImageData(size, size), nz = A.noise(seed || 3), period = 8;
    for (var y = 0; y < size; y++) for (var x = 0; x < size; x++) {
      var u = x / size * period, v = y / size * period;
      var t = Math.abs(nz.fbm(u, v, 5, period, period) - 0.5) * 2, cells = nz.fbm(u * 2 + 16, v * 2, 3, period * 2, period * 2);
      var k = clamp01(0.55 + (cells - 0.5) * 0.9 - t * 0.55), i = (y * size + x) * 4;
      img.data[i] = mix(230, 255, k); img.data[i + 1] = mix(78, 196, k); img.data[i + 2] = mix(8, 70, k * k); img.data[i + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    return c;
  };

  /** Soft teal-green + purple nebula on a transparent canvas (drawn small, scaled up = natural blur). */
  A.nebula = function (w, h, seed) {
    var c = A.canvas(w, h), g = c.getContext("2d"), img = g.createImageData(c.width, c.height), nz = A.noise(seed || 11);
    for (var y = 0; y < c.height; y++) for (var x = 0; x < c.width; x++) {
      var u = x / c.width * 3, v = y / c.height * 2;
      var teal = smoothstep(0.48, 0.8, nz.fbm(u + 3, v, 5)), violet = smoothstep(0.5, 0.82, nz.fbm(u * 1.2 + 40, v * 1.2 + 9, 5));
      var dust = nz.fbm(u * 4 + 20, v * 4, 3), i = (y * c.width + x) * 4;
      var a = clamp01(teal * 0.75 + violet * 0.8) * (0.55 + dust * 0.6);
      img.data[i] = mix(40, 150, violet / (teal + violet + 1e-3));
      img.data[i + 1] = mix(170, 70, violet / (teal + violet + 1e-3));
      img.data[i + 2] = mix(160, 210, violet / (teal + violet + 1e-3));
      img.data[i + 3] = a * 120;
    }
    g.putImageData(img, 0, 0);
    return c;
  };

  /** A small, slightly blurred background planet with a soft glow (and rings for Saturn). */
  A.planetSprite = function (def, r, blurPx) {
    var pad = r * (def.ring ? 2.6 : 2.2), size = Math.ceil(pad * 2), c = A.canvas(size, size), g = c.getContext("2d"), m = size / 2;
    if ("filter" in g && blurPx) g.filter = "blur(" + blurPx + "px)";
    var halo = g.createRadialGradient(m, m, r * 0.6, m, m, r * 2);
    halo.addColorStop(0, def.glow); halo.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = halo; g.beginPath(); g.arc(m, m, r * 2, 0, TAU); g.fill();
    if (def.ring) {
      g.strokeStyle = "rgba(226,206,150,0.75)"; g.lineWidth = Math.max(1, r * 0.28);
      g.beginPath(); g.ellipse(m, m, r * 2.2, r * 0.62, -0.32, Math.PI, TAU); g.stroke();
    }
    var body = g.createRadialGradient(m - r * 0.45, m - r * 0.35, r * 0.1, m, m, r);
    body.addColorStop(0, def.colors[0]); body.addColorStop(0.6, def.colors[1]); body.addColorStop(1, def.colors[2]);
    g.fillStyle = body; g.beginPath(); g.arc(m, m, r, 0, TAU); g.fill();
    if (def.bands) {
      g.save(); g.beginPath(); g.arc(m, m, r, 0, TAU); g.clip(); g.fillStyle = "rgba(120,80,45,0.45)";
      [-0.45, -0.1, 0.3].forEach(function (k, i) { g.fillRect(m - r, m + k * r, r * 2, r * (i === 1 ? 0.2 : 0.12)); });
      g.restore();
    }
    if (def.ring) {
      g.strokeStyle = "rgba(240,222,170,0.85)"; g.lineWidth = Math.max(1, r * 0.28);
      g.beginPath(); g.ellipse(m, m, r * 2.2, r * 0.62, -0.32, 0, Math.PI); g.stroke();
    }
    return c;
  };
})(window.ET);
