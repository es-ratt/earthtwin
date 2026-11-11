/* Page backgrounds, drawn procedurally once per window size (no image files, nothing to licence).
 *   base     : deep blue-black (#070a12) with faint star specks; under every page
 *   moon     : grey cratered regolith with a trail of footprints, black starry sky, blue Earth near the horizon
 *   mars     : rust-red curved planet horizon with a thin haze line, star field, small blue-white Earth upper right
 *   sources  : dark slate-blue star field with a warm golden-orange glow on the left
 * A layer is shown at low opacity (CSS --bg-layer-opacity) under a dark gradient, and cross-fades (CSS transition)
 * when the world or page changes. ET.Backdrop.show(name|null). */
(function (ET) {
  "use strict";

  var B = ET.Backdrop = {};
  var TAU = Math.PI * 2;
  var MAX_DPR = 1.5;                                    // backgrounds are faint: no need for full retina cost
  var layers = {}, drawnFor = "", current = null, resizeTimer = 0;

  function sizeCanvas(c) {
    var dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
    c.width = Math.round(window.innerWidth * dpr); c.height = Math.round(window.innerHeight * dpr);
    var g = c.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    return g;
  }

  function starField(g, w, h, n, seed, maxR, yMax) {
    var rnd = ET.Art.rng(seed);
    for (var i = 0; i < n; i++) {
      var x = rnd() * w, y = rnd() * h * (yMax || 1), r = 0.3 + Math.pow(rnd(), 4) * maxR, a = 0.25 + rnd() * 0.65;
      g.fillStyle = "rgba(255,255,255," + a.toFixed(2) + ")";
      g.beginPath(); g.arc(x, y, r, 0, TAU); g.fill();
    }
  }

  function earthDisc(g, x, y, r, glowA) {
    var halo = g.createRadialGradient(x, y, r * 0.8, x, y, r * 3);
    halo.addColorStop(0, "rgba(90,160,255," + glowA + ")"); halo.addColorStop(1, "rgba(90,160,255,0)");
    g.fillStyle = halo; g.beginPath(); g.arc(x, y, r * 3, 0, TAU); g.fill();
    var body = g.createRadialGradient(x - r * 0.35, y - r * 0.35, r * 0.1, x, y, r);
    body.addColorStop(0, "#bfe3ff"); body.addColorStop(0.45, "#3b8de8"); body.addColorStop(1, "#0d2f6b");
    g.fillStyle = body; g.beginPath(); g.arc(x, y, r, 0, TAU); g.fill();
    g.save(); g.beginPath(); g.arc(x, y, r, 0, TAU); g.clip();
    g.fillStyle = "rgba(255,255,255,0.7)";                  // a few cloud bands
    [[-0.3, 0.5, 0.1], [0.25, 0.45, 0.08], [0.55, 0.3, 0.07]].forEach(function (c) { g.beginPath(); g.ellipse(x + c[0] * r * 0.3, y + c[0] * r, r * c[1], r * c[2], 0.25, 0, TAU); g.fill(); });
    var night = g.createLinearGradient(x - r, y, x + r, y);   // terminator: lit from the left
    night.addColorStop(0.55, "rgba(4,8,18,0)"); night.addColorStop(1, "rgba(4,8,18,0.85)");
    g.fillStyle = night; g.fillRect(x - r, y - r, r * 2, r * 2);
    g.restore();
  }

  /** Grain over a region, from noise rendered small and scaled up (cheap and soft). */
  function grain(g, x, y, w, h, seed, rgbLo, rgbHi, alpha, freq) {
    var cw = Math.max(8, Math.round(w / 3)), ch = Math.max(8, Math.round(h / 3));
    var c = ET.Art.canvas(cw, ch), cg = c.getContext("2d"), img = cg.createImageData(cw, ch), nz = ET.Art.noise(seed);
    for (var j = 0; j < ch; j++) for (var i = 0; i < cw; i++) {
      var n = nz.fbm(i / cw * freq, j / ch * freq * (h / w) * 2.2, 5), k = (j * cw + i) * 4;
      img.data[k] = rgbLo[0] + (rgbHi[0] - rgbLo[0]) * n; img.data[k + 1] = rgbLo[1] + (rgbHi[1] - rgbLo[1]) * n;
      img.data[k + 2] = rgbLo[2] + (rgbHi[2] - rgbLo[2]) * n; img.data[k + 3] = 255 * alpha;
    }
    cg.putImageData(img, 0, 0);
    g.imageSmoothingEnabled = true;
    g.drawImage(c, x, y, w, h);
  }

  /* ------------------------------------------------------------ scenes */
  function drawBase(g, w, h) {
    g.fillStyle = "#070a12"; g.fillRect(0, 0, w, h);
    var v = g.createRadialGradient(w * 0.5, h * 0.4, Math.min(w, h) * 0.2, w * 0.5, h * 0.5, Math.max(w, h) * 0.8);
    v.addColorStop(0, "rgba(16,24,44,0.55)"); v.addColorStop(1, "rgba(2,3,8,0.6)");
    g.fillStyle = v; g.fillRect(0, 0, w, h);
    g.globalAlpha = 0.5; starField(g, w, h, Math.round(w * h / 9000), 7, 0.9); g.globalAlpha = 1;
  }

  function drawMoonScene(g, w, h) {
    g.fillStyle = "#020306"; g.fillRect(0, 0, w, h);
    starField(g, w, h, Math.round(w * h / 2600), 31, 1.4, 0.62);
    var horizon = h * 0.6;
    earthDisc(g, w * 0.7, horizon - h * 0.07, Math.min(w, h) * 0.055, 0.45);   // Earth rising over the horizon
    g.save();
    g.beginPath(); g.moveTo(0, horizon + h * 0.03);
    g.quadraticCurveTo(w * 0.5, horizon - h * 0.035, w, horizon + h * 0.02); g.lineTo(w, h); g.lineTo(0, h); g.closePath(); g.clip();
    var ground = g.createLinearGradient(0, horizon - h * 0.04, 0, h);
    ground.addColorStop(0, "#9b9a98"); ground.addColorStop(0.25, "#76757a"); ground.addColorStop(1, "#3a3a3f");
    g.fillStyle = ground; g.fillRect(0, horizon - h * 0.05, w, h);
    grain(g, 0, horizon - h * 0.05, w, h - horizon + h * 0.05, 41, [60, 60, 64], [170, 168, 166], 0.55, 22);
    var rnd = ET.Art.rng(77);
    for (var i = 0; i < 26; i++) {                       // craters, flattened by perspective
      var depth = Math.pow(rnd(), 1.6), cy = horizon + (h - horizon) * (0.05 + depth * 0.9), cr = (6 + rnd() * 30) * (0.3 + depth * 1.6);
      var cx = rnd() * w;
      g.fillStyle = "rgba(25,25,30,0.35)"; g.beginPath(); g.ellipse(cx, cy, cr, cr * 0.28, 0, 0, TAU); g.fill();
      g.strokeStyle = "rgba(220,220,215,0.25)"; g.lineWidth = 1; g.beginPath(); g.ellipse(cx, cy + cr * 0.03, cr, cr * 0.28, 0, 0.1, Math.PI - 0.1); g.stroke();
    }
    for (var s = 0; s < 22; s++) {                        // a trail of bootprints in the lower part
      var t = s / 21, fx = w * (0.18 + t * 0.34) + (s % 2 ? 9 : -9) * (0.6 + t), fy = h * (0.97 - t * 0.27);
      var sc = 1.5 - t * 0.9;
      g.fillStyle = "rgba(30,30,34,0.55)"; g.beginPath(); g.ellipse(fx, fy, 6 * sc, 2.4 * sc, -0.25, 0, TAU); g.fill();
      g.fillStyle = "rgba(210,208,204,0.25)"; g.fillRect(fx - 5 * sc, fy - 2.6 * sc, 10 * sc, 0.8);
    }
    g.restore();
    var dust = g.createLinearGradient(0, horizon - h * 0.05, 0, horizon + h * 0.05);
    dust.addColorStop(0, "rgba(190,190,195,0)"); dust.addColorStop(0.5, "rgba(190,190,195,0.12)"); dust.addColorStop(1, "rgba(190,190,195,0)");
    g.fillStyle = dust; g.fillRect(0, horizon - h * 0.05, w, h * 0.1);
  }

  function drawMarsScene(g, w, h) {
    var sky = g.createLinearGradient(0, 0, 0, h);
    sky.addColorStop(0, "#03040a"); sky.addColorStop(1, "#0b0608");
    g.fillStyle = sky; g.fillRect(0, 0, w, h);
    starField(g, w, h, Math.round(w * h / 2400), 53, 1.4, 0.75);
    earthDisc(g, w * 0.84, h * 0.17, Math.min(w, h) * 0.014, 0.6);                  // small blue-white Earth upper right
    var R = Math.max(w, h) * 1.35, cx = w * 0.45, cy = h * 0.74 + R;                  // curved planet horizon
    g.save(); g.beginPath(); g.arc(cx, cy, R, 0, TAU); g.clip();
    var surf = g.createRadialGradient(cx, cy - R, R * 0.02, cx, cy - R * 0.6, R * 0.9);
    surf.addColorStop(0, "#d4733d"); surf.addColorStop(0.3, "#9d4421"); surf.addColorStop(1, "#3b160b");
    g.fillStyle = surf; g.fillRect(0, h * 0.6, w, h);
    grain(g, 0, cy - R - 4, w, h - (cy - R) + 4, 59, [70, 26, 12], [214, 120, 70], 0.45, 14);
    var shade = g.createLinearGradient(0, cy - R, 0, h);
    shade.addColorStop(0, "rgba(0,0,0,0)"); shade.addColorStop(1, "rgba(10,4,2,0.65)");
    g.fillStyle = shade; g.fillRect(0, cy - R, w, h);
    g.restore();
    g.save(); g.globalCompositeOperation = "lighter";                                 // thin atmosphere along the limb
    [[R + 2, 0.55, 3], [R + 9, 0.18, 14], [R + 26, 0.07, 40]].forEach(function (l) {
      g.strokeStyle = "rgba(255,150,95," + l[1] + ")"; g.lineWidth = l[2];
      g.beginPath(); g.arc(cx, cy, l[0], Math.PI * 1.2, Math.PI * 1.8); g.stroke();
    });
    g.restore();
  }

  function drawSourcesScene(g, w, h) {
    var bg = g.createLinearGradient(0, 0, w, h);
    bg.addColorStop(0, "#132036"); bg.addColorStop(0.6, "#0c1424"); bg.addColorStop(1, "#070a12");
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    var glow = g.createRadialGradient(-w * 0.06, h * 0.5, 0, -w * 0.06, h * 0.5, w * 0.85);
    glow.addColorStop(0, "rgba(255,196,100,1)"); glow.addColorStop(0.22, "rgba(255,160,64,0.75)");
    glow.addColorStop(0.55, "rgba(200,100,44,0.25)"); glow.addColorStop(1, "rgba(120,60,30,0)");
    g.fillStyle = glow; g.fillRect(0, 0, w, h);
    starField(g, w, h, Math.round(w * h / 14000), 67, 1.3);
  }

  var SCENES = { base: drawBase, moon: drawMoonScene, mars: drawMarsScene, sources: drawSourcesScene };

  function drawAll() {
    var key = window.innerWidth + "x" + window.innerHeight;
    if (key === drawnFor) return;
    drawnFor = key;
    Object.keys(layers).forEach(function (name) {
      var g = sizeCanvas(layers[name]);
      SCENES[name](g, window.innerWidth, window.innerHeight);
    });
  }

  /* ------------------------------------------------------------ public */
  B.init = function () {
    document.querySelectorAll("#backdrop [data-bg]").forEach(function (c) { layers[c.dataset.bg] = c; });
    if (!ET.Art || !layers.base) return;
    drawAll();
    window.addEventListener("resize", function () { clearTimeout(resizeTimer); resizeTimer = setTimeout(drawAll, 200); });
  };

  /** Show one world/page background ("moon", "mars", "sources") or none (null); cross-fades via CSS. */
  B.show = function (name) {
    if (name === current) return;
    current = name;
    Object.keys(layers).forEach(function (k) { if (k !== "base") layers[k].classList.toggle("on", k === name); });
  };
})(window.ET);
