/* Blank-tile check + automatic fallback.
 * Some NASA tile services answer HTTP 200 with an empty image. For each layer we load one 'probe' tile
 * that is known to contain data, draw it on a canvas and look at the pixels:
 *   ok           → real pixels
 *   blank        → every pixel the same (or fully transparent) → fall back
 *   error        → failed to load → fall back
 *   unverifiable → loaded but the browser would not let us read pixels (no CORS) → keep, but say so
 * While the map is in use we also count tile errors; many errors and no successes also trigger the fallback. */
(function (ET) {
  "use strict";

  ET.layerStatus = {}; // id -> {state, name, checkedAt, url}

  function analyse(img) {
    var c = document.createElement("canvas");
    c.width = 64; c.height = 64;
    var g = c.getContext("2d");
    g.drawImage(img, 0, 0, 64, 64);
    var d = g.getImageData(0, 0, 64, 64).data;
    var first = [d[0], d[1], d[2], d[3]], varied = false, anyAlpha = false;
    for (var i = 0; i < d.length; i += 4) {
      if (d[i + 3] > 8) anyAlpha = true;
      if (!varied && (Math.abs(d[i] - first[0]) > 3 || Math.abs(d[i + 1] - first[1]) > 3 || Math.abs(d[i + 2] - first[2]) > 3 || Math.abs(d[i + 3] - first[3]) > 3)) varied = true;
    }
    return anyAlpha && varied ? "ok" : "blank";
  }

  /** Resolve to 'ok' | 'blank' | 'error' | 'unverifiable' for a layer definition. */
  ET.probeLayer = function (def, timeoutMs) {
    return new Promise(function (resolve) {
      var img = new Image();
      var done = false;
      var timer = setTimeout(function () { finish("error"); }, timeoutMs || 9000);
      function finish(state) {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve(state);
      }
      img.crossOrigin = "anonymous";
      img.onload = function () {
        try { finish(analyse(img)); } catch (e) { finish("unverifiable"); }
      };
      img.onerror = function () { finish("error"); };
      img.src = ET.probeUrl(def);
    });
  };

  function record(def, state) {
    ET.layerStatus[def.id] = { state: state, name: def.name, url: ET.probeUrl(def), checkedAt: new Date().toISOString(), source_id: def.source_id };
    document.dispatchEvent(new CustomEvent("et:layerstatus", { detail: { id: def.id, state: state } }));
  }

  /**
   * Add a guarded base layer to a map. If it fails, the static fallback image is shown instead
   * and onState(state) reports what happened (used for the badge on each map).
   */
  ET.guardLayer = function (map, def, fallbackDef, onState) {
    var layer = ET.makeLayer(def);
    var errors = 0, loads = 0, fellBack = false;
    var fallback = null;

    function useFallback(state) {
      if (fellBack) return;
      fellBack = true;
      if (map.hasLayer(layer)) map.removeLayer(layer);
      fallback = L.imageOverlay(fallbackDef.url, fallbackDef.bounds, { attribution: "STATIC FALLBACK · " + fallbackDef.name }).addTo(map);
      fallback.bringToBack();
      onState && onState("fallback", state);
    }

    layer.on("tileerror", function () {
      errors += 1;
      if (errors >= 6 && loads === 0) { record(def, "error"); useFallback("error"); }
    });
    layer.on("tileload", function () { loads += 1; });

    ET.probeLayer(def).then(function (state) {
      record(def, state);
      if (state === "blank" || state === "error") useFallback(state);
      else onState && onState(state === "ok" ? "live" : "unverified", state);
    });

    return { layer: layer, isFallback: function () { return fellBack; }, fallback: function () { return fallback; } };
  };

  /** Probe overlay/alternative layers without adding them (for the Sources → Map layers report). */
  ET.probeAll = function (defs) {
    return Promise.all(defs.map(function (def) {
      if (ET.layerStatus[def.id]) return Promise.resolve();
      return ET.probeLayer(def).then(function (state) { record(def, state); });
    }));
  };
})(window.ET);
