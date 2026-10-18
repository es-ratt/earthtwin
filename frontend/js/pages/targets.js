import * as api from '../api.js';
import { planetMap } from '../maps.js';
import { set, store } from '../store.js';
import { $, $$, esc, cls, coord, num, safeUrl } from '../ui.js';

const R = { moon: 1737.4, mars: 3396.19 };

function parseCoords(q) {
  const m = q.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (!m) return null;
  const lat = +m[1], lon = +m[2];
  if (Math.abs(lat) > 90 || lon < -180 || lon > 360) return null;
  return { lat, lon: lon > 180 ? lon - 360 : lon };
}
function gcKm(a, b, radius) {
  const r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.min(1, Math.sqrt(h)));
}

export async function render(main, [worldArg]) {
  const world = worldArg || (store.targetId && (await api.get('/api/targets')).find(t => t.id === store.targetId)?.world_id) || 'moon';
  const [targets, layers] = await Promise.all([api.get(`/api/targets?world=${world}`), api.get(`/api/layers?body=${world}`)]);
  let q = '';
  let sel = targets.find(t => t.id === store.targetId)?.id || targets[0]?.id;
  main.innerHTML = `
  <div class="phead"><div><h1 style="font-size:1.7rem">Moon &amp; Mars target explorer</h1>
    <p>Browse target regions, inspect their context and data, and choose one for Earth analog comparison. Coordinates are planetocentric latitude and east-positive longitude on each body's IAU reference sphere.</p></div>
    <a class="btn sm" href="#/data">Import target regions</a></div>
  <div class="tabs" role="tablist">
    <button role="tab" class="${world === 'moon' ? 'on' : ''}" aria-selected="${world === 'moon'}" data-w="moon">🌙 Moon</button>
    <button role="tab" class="${world === 'mars' ? 'on' : ''}" aria-selected="${world === 'mars'}" data-w="mars">Mars</button>
  </div>
  <div class="grid" style="grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr)">
    <div class="card mapcard" style="padding:0;overflow:hidden"><div id="pmap" style="height:520px" role="region" aria-label="${world} map of target regions"></div></div>
    <div class="card stack"><label class="field"><span>Search by name or coordinates (lat, lon)</span><input id="tq" type="search" placeholder="e.g. Jezero  or  18.4, 77.6"></label>
      <div id="tlist" class="panel-scroll" style="max-height:440px"></div></div>
  </div>
  <div class="card" id="tdet" style="margin-top:14px"></div>
  <p class="small dim" style="margin-top:8px">Imagery: ${layers.filter(l => l.kind === 'tiles').map(l => esc(l.name)).join(' · ') || 'none configured'} — visual context only, never used in scoring. Polar targets are strongly distorted in this equirectangular view; a polar-stereographic view is listed as future work.</p>`;
  $$('.tabs button', main).forEach(b => b.addEventListener('click', () => { location.hash = `#/targets/${b.dataset.w}`; }));
  const pm = await planetMap($('#pmap'), world, { onSelect: id => pick(id) });

  function list() {
    const c = parseCoords(q);
    let items = targets.map(t => ({ ...t, dist: c ? gcKm(c, t, R[world]) : null }));
    if (c) items.sort((a, b) => a.dist - b.dist);
    else if (q) items = items.filter(t => `${t.name} ${t.region_type || ''} ${(t.tags || []).join(' ')}`.toLowerCase().includes(q.toLowerCase()));
    $('#tlist').innerHTML = items.length ? items.map(t => `<div class="rankitem ${t.id === sel ? 'sel' : ''}" tabindex="0" data-id="${esc(t.id)}" style="grid-template-columns:minmax(0,1fr) auto">
      <span class="nm">${esc(t.name)}<small>${coord(t.lat, t.lon)}${t.dist !== null ? ' · ' + num(t.dist, 0) + ' km away' : ''}</small></span>
      <span class="small dim">${t.completeness.variables_available}/${t.completeness.variables_total}</span></div>`).join('')
      : `<div class="empty small">${targets.length ? 'No target matches.' : `<h3>No ${world} targets yet</h3>Import target regions in the Data Center.`}</div>`;
    $$('#tlist .rankitem').forEach(el => {
      el.addEventListener('click', () => pick(el.dataset.id));
      el.addEventListener('keydown', e => { if (e.key === 'Enter') pick(el.dataset.id); });
    });
  }

  async function detail() {
    const el = $('#tdet');
    if (!sel) { el.innerHTML = '<div class="empty">No target selected.</div>'; return; }
    const t = await api.get(`/api/targets/${encodeURIComponent(sel)}`);
    el.innerHTML = targetDetail(t, true);
    $('#usebtn', el)?.addEventListener('click', () => { set({ targetId: t.id, selected: null }); location.hash = '#/explore'; });
  }

  function pick(id) { sel = id; pm.setTargets(targets, sel); list(); detail(); }
  $('#tq').addEventListener('input', e => { q = e.target.value.trim(); list(); });
  pm.setTargets(targets, sel);
  list();
  await detail();
  return { destroy() { pm.map.remove(); } };
}

export function targetDetail(t, withLink) {
  const obs = t.observations || [];
  return `
  <div class="row between"><div><h2 style="margin:0">${esc(t.name)}</h2>
    <span class="small muted">${esc(t.world?.name || t.world_id)} · ${coord(t.lat, t.lon)} (planetocentric, east-positive) · CRS <code>${esc(t.crs)}</code> · analysis window ${num(t.analysis_radius_km)} km radius</span></div>
    <div class="row">${withLink ? `<a class="btn sm" href="#/target/${encodeURIComponent(t.id)}">Full profile</a>` : ''}<button class="btn primary sm" id="usebtn">Find Earth analogs →</button></div></div>
  <hr class="sep">
  <div class="grid g2">
    <div><h4>Description</h4><p>${esc(t.description || 'No description recorded.')}</p>
      <h4>Geological context</h4><p>${esc(t.geologic_context || 'Not documented.')}</p>
      <h4>Mission relevance</h4><p>${esc(t.mission_relevance || 'Not documented.')}</p>
      <div class="row">${(t.tags || []).map(x => `<span class="tag">${esc(x)}</span>`).join('')}</div></div>
    <div><h4>Measurements (${obs.length})</h4>
      ${obs.length ? `<div class="tablewrap"><table><thead><tr><th>Variable</th><th>Value</th><th>Class</th><th>Source</th></tr></thead><tbody>
        ${obs.map(o => `<tr><td>${esc(o.variable_key)}</td><td>${Array.isArray(o.value) ? o.value.map(v => esc(v)).join(', ') : esc(typeof o.value === 'number' ? num(o.value) : o.value)} <span class="dim">${esc(o.unit || '')}</span></td><td>${cls(o.data_class)}</td><td class="small"><a href="#/dataset/${encodeURIComponent(o.dataset_id)}">${esc(o.dataset_name)}</a></td></tr>`).join('')}
        </tbody></table></div>` : '<div class="empty small">No measurements yet. Import a LOLA/MOLA DEM or a target observation table to enable comparisons.</div>'}
      <p class="small muted">Data coverage: ${t.completeness.variables_available}/${t.completeness.variables_total} scoring variables. Missing: ${t.completeness.missing.map(esc).join(', ') || 'none'}.</p></div>
  </div>
  ${(t.citations || []).length ? `<h4>Sources</h4><ul class="small">${t.citations.map(c => `<li>${esc(c.text)} ${safeUrl(c.url) ? `<a href="${safeUrl(c.url)}" target="_blank" rel="noopener">link</a>` : ''} <span class="dim">[${esc(c.verification)}]</span></li>`).join('')}</ul>` : ''}`;
}
