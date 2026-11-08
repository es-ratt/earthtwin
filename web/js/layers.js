/* Map layers and projections. Every URL here was tested on 2026-11-09 (see README_DATA.md → "Map layers").
 * Change a layer: edit LAYERS below. Each layer has a 'probe' tile known to contain data, used by tiles-check.js. */
(function (ET, L) {
  "use strict";

  /* ------------------------------------------------------------------
   * Moon south polar stereographic (sphere R = 1737.4 km), the same grid
   * NASA Moon Trek uses for its /Moon/SP/ tiles:
   *   x = ρ·sin(λ), y = ρ·cos(λ), ρ = 2R·tan(π/4 + φ/2)   (φ negative in the south)
   * Trek tile matrix (from WMTSCapabilities.xml, set "default028mm"):
   *   origin (−1095930, 1095930) m, level-0 pixel = 8561.953125 m, 2×1 tiles at level 0.
   * Orientation checked by placing Shackleton, de Gerlache and Haworth on the tiles.
   * ------------------------------------------------------------------ */
  var R_MOON = 1737400;
  var TREK_SP_ORIGIN = 1095930;
  var TREK_SP_RES0 = 8561.953125;

  var MoonSouthPolar = {
    project: function (latlng) {
      var phi = latlng.lat * Math.PI / 180, lam = latlng.lng * Math.PI / 180;
      var rho = 2 * R_MOON * Math.tan(Math.PI / 4 + phi / 2);
      return L.point(rho * Math.sin(lam), rho * Math.cos(lam));
    },
    unproject: function (p) {
      var rho = Math.sqrt(p.x * p.x + p.y * p.y);
      var lat = (2 * Math.atan(rho / (2 * R_MOON)) - Math.PI / 2) * 180 / Math.PI;
      var lng = rho === 0 ? 0 : Math.atan2(p.x, p.y) * 180 / Math.PI;
      return L.latLng(lat, lng);
    },
    bounds: L.bounds([-TREK_SP_ORIGIN, -TREK_SP_ORIGIN], [3 * TREK_SP_ORIGIN, TREK_SP_ORIGIN])
  };

  ET.CRS_MOON_SP = L.extend({}, L.CRS, {
    code: "EPSG:32761", // the code USGS Astrogeology's moon_spole WMS answers to (pole-centred metres)
    projection: MoonSouthPolar,
    transformation: new L.Transformation(1 / TREK_SP_RES0, TREK_SP_ORIGIN / TREK_SP_RES0, -1 / TREK_SP_RES0, TREK_SP_ORIGIN / TREK_SP_RES0),
    scale: function (z) { return Math.pow(2, z); },
    zoom: function (s) { return Math.log(s) / Math.LN2; },
    distance: function (a, b) { var p = MoonSouthPolar.project(a), q = MoonSouthPolar.project(b); return Math.hypot(p.x - q.x, p.y - q.y); },
    infinite: true,
    wrapLng: null
  });
  ET.moonProject = MoonSouthPolar.project;
  ET.moonUnproject = MoonSouthPolar.unproject;

  /** Only request tiles that exist in the Trek matrix and overlap the layer's data square (±extent m). */
  function polarValidTile(coords) {
    var z = coords.z;
    if (coords.x < 0 || coords.y < 0 || coords.x >= 2 * Math.pow(2, z) || coords.y >= Math.pow(2, z)) return false;
    var size = 256 * TREK_SP_RES0 / Math.pow(2, z);
    var x0 = -TREK_SP_ORIGIN + coords.x * size, y0 = TREK_SP_ORIGIN - coords.y * size;
    var e = this.options.extentM || 457440;
    return !(x0 > e || x0 + size < -e || y0 < -e || y0 - size > e);
  }
  ET.PolarTileLayer = L.TileLayer.extend({ _isValidTile: polarValidTile });
  ET.PolarWMSLayer = L.TileLayer.WMS.extend({ _isValidTile: polarValidTile });

  var TREK = "https://trek.nasa.gov/tiles";
  var USGS_WMS = "https://planetarymaps.usgs.gov/cgi-bin/mapserv";
  var GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best";

  function trekSP(layer, ext) { return TREK + "/Moon/SP/" + layer + "/1.0.0/default/default028mm/{z}/{y}/{x}." + ext; }
  function trekEQ(body, layer, ext) { return TREK + "/" + body + "/EQ/" + layer + "/1.0.0/default/default028mm/{z}/{y}/{x}." + ext; }

  /* Static fallbacks (shipped with the site). Bounds are in each map's own CRS. */
  var moonCornerNW = MoonSouthPolar.unproject(L.point(-457440, 457440));
  var moonCornerSE = MoonSouthPolar.unproject(L.point(457440, -457440));

  ET.LAYERS = {
    moon: {
      crs: "moon-sp",
      view: { center: [-90, 0], zoom: 2, minZoom: 1, maxZoom: 8 },
      base: [
        { id: "trek-lola-clrshade", name: "LOLA colour hillshade · NASA Moon Trek", type: "polar-tile", source_id: "map-trek-moon",
          url: trekSP("LRO_LOLA_ClrShade_SPole75_30mp_v04", "png"), maxNativeZoom: 6, extentM: 457440,
          probe: { z: 2, x: 1, y: 1 }, attribution: "NASA/GSFC/LOLA · Moon Trek" },
        { id: "trek-lola-shade", name: "LOLA hillshade · NASA Moon Trek", type: "polar-tile", source_id: "map-trek-moon",
          url: trekSP("LRO_LOLA_Shade_SPole75_30mp_v04", "png"), maxNativeZoom: 6, extentM: 457440,
          probe: { z: 2, x: 1, y: 1 }, attribution: "NASA/GSFC/LOLA · Moon Trek" },
        { id: "usgs-lroc-wac-south", name: "LROC WAC mosaic · USGS Astrogeology", type: "polar-wms", source_id: "map-usgs-astro",
          url: USGS_WMS + "?map=/maps/earth/moon_spole.map", layers: "LRO_WAC_south", extentM: 457440,
          probe: { bbox: "-457440,-457440,457440,457440" }, attribution: "NASA/ASU LROC · USGS Astrogeology" }
      ],
      overlays: [
        { id: "trek-psr", name: "Permanently shadowed regions (LOLA)", type: "polar-tile", source_id: "map-trek-moon",
          url: trekSP("LRO_LOLA_Illumination_SPole65S_240m", "png"), maxNativeZoom: 3, extentM: 770640, opacity: 0.85,
          probe: { z: 2, x: 1, y: 1 }, attribution: "NASA/GSFC/LOLA" },
        { id: "trek-slope", name: "Slope, colourised (LOLA 120 m)", type: "polar-tile", source_id: "map-trek-moon",
          url: trekSP("LRO_LOLA_ClrSlope_SPole75S_120m", "png"), maxNativeZoom: 4, extentM: 457440, opacity: 0.75,
          probe: { z: 2, x: 1, y: 1 }, attribution: "NASA/GSFC/LOLA" }
      ],
      fallback: { url: "img/fallback/moon_usgs_lola_south_75S_polar.jpg", bounds: [[moonCornerNW.lat, moonCornerNW.lng], [moonCornerSE.lat, moonCornerSE.lng]],
        name: "USGS LOLA south pole (static copy, 75°S–90°S)" }
    },

    mars: {
      crs: "eq",
      view: { center: [40, -170], zoom: 3, minZoom: 1, maxZoom: 9 },
      base: [
        { id: "trek-mdim21", name: "Viking MDIM 2.1 colour · NASA Mars Trek", type: "tile", source_id: "map-trek-mars",
          url: trekEQ("Mars", "Mars_Viking_MDIM21_ClrMosaic_global_232m", "jpg"), maxNativeZoom: 7,
          probe: { z: 2, x: 1, y: 0 }, attribution: "NASA/USGS Viking MDIM 2.1 · Mars Trek" },
        { id: "trek-mola-clrshade", name: "MOLA colour hillshade · NASA Mars Trek", type: "tile", source_id: "map-trek-mars",
          url: trekEQ("Mars", "Mars_MGS_MOLA_ClrShade_merge_global_463m", "jpg"), maxNativeZoom: 6,
          probe: { z: 2, x: 1, y: 0 }, attribution: "NASA/GSFC MOLA · Mars Trek" },
        { id: "usgs-themis", name: "THEMIS day IR · USGS Astrogeology", type: "wms", source_id: "map-usgs-astro",
          url: USGS_WMS + "?map=/maps/mars/mars_simp_cyl.map", layers: "THEMIS",
          probe: { bbox: "-170,35,-150,50" }, attribution: "NASA/ASU THEMIS · USGS Astrogeology" }
      ],
      overlays: [
        { id: "usgs-mola-color", name: "MOLA elevation colour · USGS", type: "wms", source_id: "map-usgs-astro",
          url: USGS_WMS + "?map=/maps/mars/mars_simp_cyl.map", layers: "MOLA_color", opacity: 0.6,
          probe: { bbox: "-180,-90,180,90" }, attribution: "NASA/GSFC MOLA · USGS Astrogeology" }
      ],
      fallback: { url: "img/fallback/mars_trek_mdim21_eq.jpg", bounds: [[-90, -180], [90, 180]], name: "Viking MDIM 2.1 (static copy)" }
    },

    earth: {
      crs: "web-mercator",
      view: { center: [45, -40], zoom: 2, minZoom: 1, maxZoom: 12 },
      base: [
        { id: "gibs-bluemarble", name: "Blue Marble shaded relief · NASA GIBS", type: "tile", source_id: "map-gibs",
          url: GIBS + "/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg", maxNativeZoom: 8,
          probe: { z: 2, x: 1, y: 1 }, attribution: "NASA Blue Marble · GIBS" },
        { id: "gibs-aster-relief", name: "ASTER GDEM colour relief · NASA GIBS", type: "tile", source_id: "map-gibs",
          url: GIBS + "/ASTER_GDEM_Color_Shaded_Relief/default/GoogleMapsCompatible_Level12/{z}/{y}/{x}.jpeg", maxNativeZoom: 12,
          probe: { z: 4, x: 3, y: 6 }, attribution: "NASA/METI ASTER GDEM · GIBS" }
      ],
      overlays: [
        { id: "gibs-modis-lst", name: "MODIS land surface temperature, day (8-day, 2026-07-04)", type: "tile", source_id: "map-gibs",
          url: GIBS + "/MODIS_Terra_L3_Land_Surface_Temp_8Day_Day/default/2026-07-04/GoogleMapsCompatible_Level7/{z}/{y}/{x}.png", maxNativeZoom: 7, opacity: 0.7,
          probe: { z: 2, x: 1, y: 1 }, attribution: "NASA MODIS · GIBS" }
      ],
      fallback: { url: "img/fallback/earth_gibs_bluemarble_3857.jpg", bounds: [[-85.0511, -180], [85.0511, 180]], name: "Blue Marble (static copy)" }
    }
  };

  /** URL of a layer's probe tile (or WMS image) for the blank-tile check. */
  ET.probeUrl = function (def) {
    if (def.type === "wms" || def.type === "polar-wms") {
      var srs = def.type === "polar-wms" ? "EPSG:32761" : "EPSG:4326";
      return def.url + "&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=" + encodeURIComponent(def.layers) +
        "&STYLES=&SRS=" + srs + "&BBOX=" + def.probe.bbox + "&WIDTH=128&HEIGHT=128&FORMAT=image/png";
    }
    return def.url.replace("{z}", def.probe.z).replace("{x}", def.probe.x).replace("{y}", def.probe.y);
  };

  /** Build a Leaflet layer from a definition. */
  ET.makeLayer = function (def) {
    var common = { attribution: def.attribution, opacity: def.opacity === undefined ? 1 : def.opacity, crossOrigin: "anonymous",
      maxNativeZoom: def.maxNativeZoom, maxZoom: 12, extentM: def.extentM, tileSize: 256 };
    if (def.type === "polar-tile") return new ET.PolarTileLayer(def.url, common);
    if (def.type === "tile") return L.tileLayer(def.url, L.extend(common, { noWrap: false }));
    var wms = L.extend(common, { layers: def.layers, format: "image/png", transparent: def.opacity !== undefined, version: "1.1.1", styles: "" });
    delete wms.maxNativeZoom;
    if (def.type === "polar-wms") return new ET.PolarWMSLayer(def.url, wms);
    return L.tileLayer.wms(def.url, wms);
  };
})(window.ET, window.L);
