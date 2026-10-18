import * as api from '../api.js';
import * as AS from '../assess.js';
import { bindTips } from '../charts.js';
import { demoNote, loadCommon, targetSelect } from '../components.js';
import { earthMap } from '../maps.js';
import { analysisBody, set, store, toggleCompare } from '../store.js';
import { $, esc, cls, citeList, coord, num, meter, CAT_LABEL, toast, value } from '../ui.js';

export async function render(main, [id]) {
  const [s, { vocab, targets }] = await Promise.all([api.get(`/api/sites/${encodeURIComponent(id)}?include_demo=${store.includeDemo}`), loadCommon()]);
  const names = Object.fromEntries(vocab.criteria.map(c => [c.key, c.name]));
  const vars = Object.fromEntries(vocab.variables.map(v => [v.key, v]));
  const fams = ['terrain', 'geology', 'environment', 'resources', 'operational'];
  const list = (a, empty) => (a && a.length ? `<ul>${a.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : `<p class="small dim">${empty}</p>`);
  const extra = Object.entries(s.extra || {});
  main.innerHTML = `
  <div class="crumbs"><a href="#/catalogue">Catalogue</a> / ${esc(s.country || '')}</div>
  <div class="phead"><div><h1 style="font-size:1.9rem">${esc(s.name)}</h1>
    <p>${esc([s.region, s.country].filter(Boolean).join(', '))} · ${coord(s.lat, s.lon)} (WGS 84) · ${s.categories.map(c => esc(CAT_LABEL[c] || c)).join(' · ')}</p></div>
    <div class="row"><button class="btn" id="cmpbtn">${store.compare.includes(s.id) ? '✓ In comparison' : '+ Add to comparison'}</button></div></div>
  <div class="grid" style="grid-template-columns:minmax(0,1.3fr) minmax(0,1fr)">
    <div class="card"><h4>Overview</h4><p>${esc(s.description || 'No description recorded.')}</p>
      <h4>Geological context</h4><p>${esc(s.geologic_context || 'Not documented.')}</p>
      <h4>Documented analog heritage</h4><p>${esc(s.analog_heritage || 'None recorded in the catalogue.')}</p>
      ${s.terrain_type ? `<p class="small muted">Terrain type: ${esc(s.terrain_type)} · analysis window ${num(s.analysis_radius_km)} km radius</p>` : ''}</div>
    <div class="card mapcard" style="padding:0;overflow:hidden"><div id="smap" style="height:100%;min-height:300px"></div></div>
  </div>

  <section class="card" style="margin-top:14px">
    <div class="row between"><h2 style="margin:0">Similarity to a target region</h2><div style="min-width:280px">${targetSelect(targets, 'stsel')}</div></div>
    <div id="assess" style="margin-top:12px"></div>
  </section>

  <section class="card" style="margin-top:14px">
    <div class="row between"><h2 style="margin:0">Measurements &amp; evidence</h2>
      <span class="small muted">${s.completeness.variables_available}/${s.completeness.variables_total} scoring variables available <span style="display:inline-block;width:120px;vertical-align:middle">${meter(s.completeness.fraction, true)}</span></span></div>
    ${s.observations.length ? `<div class="tablewrap" style="margin-top:10px"><table><thead><tr><th>Variable</th><th>Value</th><th>Class</th><th>Method / spatial support</th><th>Dataset</th></tr></thead><tbody>
      ${fams.flatMap(f => s.observations.filter(o => vars[o.variable_key]?.family === f).map(o => `<tr>
        <td>${esc(vars[o.variable_key]?.name || o.variable_key)}<br><span class="small dim">${esc(f)}</span></td>
        <td>${value(o.value, o.unit)}${o.uncertainty !== null ? ` <span class="dim">± ${num(o.uncertainty)}</span>` : ''}${o.original_unit && o.original_unit !== o.unit ? `<br><span class="small dim">imported as ${esc(o.original_value)} ${esc(o.original_unit)}</span>` : ''}</td>
        <td>${cls(o.data_class)}</td><td class="small">${esc(o.method || '')}${o.spatial_support ? `<br><span class="dim">${esc(o.spatial_support)}</span>` : ''}</td>
        <td class="small"><a href="#/dataset/${encodeURIComponent(o.dataset_id)}">${esc(o.dataset_name)}</a> <span class="dim">${esc(o.dataset_version)}</span></td></tr>`)).join('')}
      </tbody></table></div>` : '<div class="empty" style="margin-top:10px">No measurements for this site yet. Import a site observation table or process a DEM in the Data Center.</div>'}
    ${s.completeness.missing.length ? `<p class="small muted" style="margin-top:8px">Not yet available: ${s.completeness.missing.map(k => esc(vars[k]?.name || k)).join(', ')}.</p>` : ''}
  </section>

  <div class="grid g3" style="margin-top:14px">
    <div class="card"><h3>Potential research &amp; field-testing applications</h3>${list(s.applications, 'None recorded.')}</div>
    <div class="card"><h3>Known limitations</h3>${list(s.limitations, 'None recorded.')}<p class="small muted">No Earth site reproduces lunar or Martian gravity, vacuum/thin CO₂ atmosphere or surface radiation.</p></div>
    <div class="card"><h3>Suggested future investigations</h3>${list(s.future_work, 'None recorded.')}</div>
  </div>
  ${extra.length ? `<div class="card" style="margin-top:14px"><h3>Additional imported fields</h3><p class="small dim">Columns preserved from imports that do not map to an EarthTwin field.</p><table>${extra.map(([k, v]) => `<tr><td class="dim">${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table></div>` : ''}
  <div class="card" style="margin-top:14px"><h3>Sources &amp; citations</h3>${citeList(s.citations)}
    <p class="small dim">Record source: ${cls(s.data_class)} catalogue record${s.source_dataset_id ? ` from <a href="#/dataset/${encodeURIComponent(s.source_dataset_id)}">its dataset</a>` : ''}.</p></div>`;

  const m = await earthMap($('#smap'), { compact: true });
  m.setSites([s]);
  m.map.setView([s.lat, s.lon], 5);

  async function assess() {
    const el = $('#assess');
    el.innerHTML = '<p class="small muted">Scoring…</p>';
    try {
      const res = await api.rank(analysisBody());
      const r = res.results.find(x => x.site.id === s.id);
      el.innerHTML = r ? `${demoNote(res)}<p class="small muted">Profile “${esc(res.profile_name)}” (change weights in the <a href="#/explore">Explorer</a>). Rank ${r.rank ?? '—'} of ${res.n_scored} scored candidates.</p>
        ${AS.summary(r)}<hr class="sep">${AS.chart(r)}<hr class="sep">${AS.evidence(r, names)}
        <details style="margin-top:10px"><summary class="small" style="cursor:pointer">Criterion table</summary>${AS.table(r)}</details>` : '<p class="muted">This site is not part of the active analysis.</p>';
      bindTips(el);
    } catch (e) { el.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; }
  }
  $('#stsel').addEventListener('change', e => { set({ targetId: e.target.value }); assess(); });
  $('#cmpbtn').addEventListener('click', e => {
    if (!toggleCompare(s.id)) return toast('The comparison holds up to 3 sites.', true);
    e.target.textContent = store.compare.includes(s.id) ? '✓ In comparison' : '+ Add to comparison';
  });
  await assess();
  return { destroy() { m.map.remove(); } };
}
