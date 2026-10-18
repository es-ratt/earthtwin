// Map system. Earth uses Web Mercator (Leaflet default) with WGS 84 lon/lat.
// The Moon and Mars use a separate equirectangular map (planetocentric lat,
// east-positive lon on each body's reference sphere). Planetary coordinates are
// never drawn on an Earth map.
import * as api from './api.js';
import { esc } from './ui.js';
import { scoreColor } from './charts.js';

const L = window.L;
let landCache;

async function naturalEarth() {
  if (!landCache) landCache = fetch('data/ne_110m_land.geojson').then(r => r.json()).catch(() => null);
  return landCache;
}

function graticule(step = 30) {
  const lines = [];
  for (let lon = -180; lon <= 180; lon += step) lines.push([[-90, lon], [90, lon]]);
  for (let lat = -90; lat <= 90; lat += step) lines.push([[lat, -180], [lat, 180]]);
  return L.polyline(lines, { color: '#2a3857', weight: 1, interactive: false });
}

function legendControl(html) {
  const c = L.control({ position: 'bottomleft' });
  c.onAdd = () => { const d = L.DomUtil.create('div', 'maplegend'); d.innerHTML = html; L.DomEvent.disableClickPropagation(d); return d; };
  return c;
}

async function addDbLayers(map, body, control, baseFallback) {
  let layers = [];
  try { layers = await api.get(`/api/layers?body=${body}`); } catch { /* offline: keep fallback only */ }
  const bases = {};
  let firstTile = null;
  for (const l of layers) {
    if (l.kind === 'tiles') {
      const opts = body === 'earth' ? { maxNativeZoom: 8, maxZoom: 12, attribution: esc(l.attribution) }
        : { maxNativeZoom: 7, maxZoom: 10, attribution: esc(l.attribution), noWrap: true, tms: false };
      const t = L.tileLayer(l.tile_url, opts);
      let errors = 0;
      t.on('tileerror', () => {
        errors++;
        if (errors === 6) {
          map.fire('et:tileerror', { name: l.name });
          if (map.hasLayer(t)) { map.removeLayer(t); baseFallback.layer.addTo(map); }
        }
      });
      bases[esc(l.name)] = t;
      if (!firstTile) firstTile = t;
    }
  }
  bases[baseFallback.name] = baseFallback.layer;
  const overlays = {};
  for (const l of layers.filter(x => x.kind === 'vector')) {
    try {
      const gj = await api.get(`/api/layers/${l.id}/geojson`);
      const color = (l.legend && l.legend.color) || '#38bdf8';
      const labelProp = l.legend && l.legend.label_property;
      overlays[`${esc(l.name)} <span class="cls ${esc(l.data_class)}">${esc(l.data_class)}</span>`] = L.geoJSON(gj, {
        style: { color, weight: 1.5, fillOpacity: 0.12 },
        pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 4, color, weight: 1, fillOpacity: 0.8 }),
        onEachFeature: (f, lyr) => {
          const p = f.properties || {};
          const title = labelProp && p[labelProp] !== undefined ? p[labelProp] : (p.name || p.NAME || '');
          const rows = Object.entries(p).slice(0, 8).map(([k, v]) => `<tr><td class="dim">${esc(k)}</td><td>${esc(v)}</td></tr>`).join('');
          lyr.bindPopup(`<b>${esc(title)}</b><br><span class="dim small">${esc(l.name)} · ${esc(l.dataset_name)}</span><table class="small">${rows}</table>`);
        },
      });
    } catch { /* skip broken layer */ }
  }
  const ctl = L.control.layers(bases, overlays, { collapsed: true }).addTo(map);
  (firstTile || baseFallback.layer).addTo(map);
  return ctl;
}

export async function earthMap(el, { onSelect, compact = false } = {}) {
  const map = L.map(el, { worldCopyJump: true, minZoom: 1, zoomSnap: 0.5, attributionControl: true, scrollWheelZoom: !compact })
    .setView([20, 0], compact ? 1 : 1.5);
  const outline = L.layerGroup();
  graticule().addTo(outline);
  naturalEarth().then(gj => { if (gj) L.geoJSON(gj, { style: { color: '#33507a', weight: 0.8, fillColor: '#13213a', fillOpacity: 1 }, interactive: false }).addTo(outline); });
  await addDbLayers(map, 'earth', null, { name: 'Natural Earth outlines (offline)', layer: outline });
  const markers = L.layerGroup().addTo(map);
  if (!compact) {
    legendControl(`<b>Similarity index</b><br>${[[80, '80–100'], [60, '60–80'], [40, '40–60'], [20, '20–40'], [0, '0–20']].map(([v, t]) => `<span class="sw" style="background:${scoreColor(v)}"></span>${t}`).join('<br>')}<br><span class="sw" style="background:transparent;border:1.5px dashed #6c7a93"></span>insufficient data`).addTo(map);
  }
  map.on('et:tileerror', e => {
    const n = L.DomUtil.create('div', 'mapnote');
    n.innerHTML = `<span>Online imagery "${esc(e.name)}" is unavailable — showing offline outlines.</span>`;
    el.appendChild(n);
  });
  let byId = {};
  let fitted = false;
  return {
    map,
    setResults(results, selected) {
      markers.clearLayers();
      if (!fitted && results.length) {
        fitted = true;
        map.fitBounds(L.latLngBounds(results.map(r => [r.site.lat, r.site.lon])).pad(0.15), { maxZoom: 3 });
      }
      byId = {};
      results.forEach(r => {
        const col = scoreColor(r.status === 'scored' ? r.score : null);
        const m = L.circleMarker([r.site.lat, r.site.lon], {
          radius: r.site.id === selected ? 10 : 7, color: r.site.id === selected ? '#22d3ee' : (col ? '#0d1424' : '#6c7a93'),
          weight: r.site.id === selected ? 3 : 2, dashArray: col ? null : '3 3', fillColor: col || '#0d1424', fillOpacity: col ? 0.95 : 0.6,
        });
        m.bindTooltip(`<b>${esc(r.site.name)}</b><br>${r.status === 'scored' ? 'Index ' + r.score.toFixed(1) + ' · rank ' + r.rank : 'Insufficient data'}<br><span class="dim">coverage ${Math.round(r.coverage * 100)}%</span>`, { direction: 'top' });
        m.on('click', () => onSelect && onSelect(r.site.id));
        m.on('keypress', e => { if (e.originalEvent.key === 'Enter') onSelect && onSelect(r.site.id); });
        m.addTo(markers);
        byId[r.site.id] = m;
      });
    },
    setSites(sites, onClick) {
      markers.clearLayers();
      if (!fitted && sites.length > 1) {
        fitted = true;
        map.fitBounds(L.latLngBounds(sites.map(x => [x.lat, x.lon])).pad(0.1), { maxZoom: 3 });
      }
      sites.forEach(s => {
        const m = L.circleMarker([s.lat, s.lon], { radius: 6, color: '#0d1424', weight: 2, fillColor: '#22d3ee', fillOpacity: 0.9 });
        m.bindTooltip(`<b>${esc(s.name)}</b><br><span class="dim">${esc(s.country || '')}</span>`);
        if (onClick) m.on('click', () => onClick(s.id));
        m.addTo(markers);
      });
    },
    focus(id) { const m = byId[id]; if (m) { map.panTo(m.getLatLng(), { animate: true }); m.bringToFront(); } },
  };
}

export async function planetMap(el, body, { onSelect } = {}) {
  const map = L.map(el, { crs: L.CRS.EPSG4326, minZoom: 0, maxZoom: 9, zoomSnap: 0.5, maxBounds: [[-95, -200], [95, 200]], worldCopyJump: false })
    .setView([0, 0], 0.5);
  const grat = graticule(30);
  await addDbLayers(map, body, null, { name: 'Graticule only (offline)', layer: grat });
  map.attributionControl.setPrefix(`${body === 'moon' ? 'Moon' : 'Mars'} · planetocentric lat / east lon · equirectangular`);
  const markers = L.layerGroup().addTo(map);
  map.on('et:tileerror', e => {
    const n = L.DomUtil.create('div', 'mapnote');
    n.innerHTML = `<span>Planetary imagery "${esc(e.name)}" could not be loaded (offline?). Coordinates and graticule remain accurate.</span>`;
    el.appendChild(n);
  });
  return {
    map,
    setTargets(targets, selected) {
      markers.clearLayers();
      targets.forEach(t => {
        const sel = t.id === selected;
        const m = L.circleMarker([t.lat, t.lon], { radius: sel ? 10 : 7, color: sel ? '#22d3ee' : '#0d1424', weight: sel ? 3 : 2, fillColor: '#f5a524', fillOpacity: 0.95 });
        m.bindTooltip(`<b>${esc(t.name)}</b><br><span class="dim">${t.lat.toFixed(2)}°, ${t.lon.toFixed(2)}°E</span>${Math.abs(t.lat) > 75 ? '<br><span class="dim">polar: strongly distorted in this projection</span>' : ''}`);
        m.on('click', () => onSelect && onSelect(t.id));
        m.addTo(markers);
      });
      const s = targets.find(t => t.id === selected);
      if (s && targets.length === 1 && Math.abs(s.lat) < 70) map.setView([s.lat, s.lon], 3);
      else if (!this._fit) { this._fit = true; map.fitBounds([[-90, -180], [90, 180]]); }
      else if (s) map.panTo([s.lat, s.lon]);
    },
  };
}
