import * as api from '../api.js';
import * as AS from '../assess.js';
import { bindTips } from '../charts.js';
import { bindWeights, demoNote, loadCommon, targetSelect, weightsPanel } from '../components.js';
import { earthMap } from '../maps.js';
import { store, set, analysisBody, toggleCompare } from '../store.js';
import { $, $$, esc, cls, coord, CAT_LABEL, errorBox, indexCell, pct, toast, WORLD } from '../ui.js';

export async function render(main, _args, query) {
  if (query.get('target')) set({ targetId: query.get('target') });
  const { vocab, targets } = await loadCommon();
  const names = Object.fromEntries(vocab.criteria.map(c => [c.key, c.name]));
  const filters = { q: '', cat: '', hideInsufficient: false };
  let result = null;

  main.innerHTML = `
  <div class="phead"><div><h1 style="font-size:1.7rem">Analog Explorer</h1>
    <p>Rank Earth sites against a Moon or Mars target. Map, ranking and details stay in sync; change weights to see how the ranking responds.</p></div>
    <div class="row noprint"><a class="btn sm" id="csvbtn">Export CSV</a><a class="btn sm" href="#/reports">Report (PDF)</a></div></div>
  <div class="explorer">
    <aside class="card stack" aria-label="Analysis settings">
      ${targetSelect(targets)}
      <div id="tsum" class="small"></div>
      <hr class="sep">
      ${weightsPanel(vocab)}
      <hr class="sep">
      <h4>Filter candidates</h4>
      <label class="field"><span>Search</span><input id="fq" type="search" placeholder="name or country"></label>
      <label class="field"><span>Analog category</span><select id="fcat"><option value="">All categories</option>
        ${Object.entries(vocab.site_categories).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('')}</select></label>
      <label class="check"><input type="checkbox" id="fins"> Hide “insufficient data”</label>
    </aside>
    <section class="stack" style="min-width:0">
      <div class="card mapcard"><div class="map" id="emap" role="region" aria-label="Interactive Earth map of candidate analog sites"></div></div>
      <div class="card" id="status" aria-live="polite"></div>
      <div class="card" id="detail"></div>
    </section>
    <aside class="card rankcol" aria-label="Candidate ranking">
      <div class="row between"><h3 style="margin:0">Ranking</h3><span class="small dim" id="rcount"></span></div>
      <div id="rnote"></div>
      <div class="panel-scroll" id="rlist" role="listbox" aria-label="Ranked candidates"></div>
    </aside>
  </div>`;

  const m = await earthMap($('#emap'), { onSelect: id => select(id, false) });

  function visible() {
    if (!result) return [];
    return result.results.filter(r => {
      if (filters.hideInsufficient && r.status !== 'scored') return false;
      if (filters.cat && !r.site.categories.includes(filters.cat)) return false;
      if (filters.q) {
        const q = filters.q.toLowerCase();
        if (!(`${r.site.name} ${r.site.country || ''}`.toLowerCase().includes(q))) return false;
      }
      return true;
    });
  }

  function drawTarget() {
    const t = targets.find(x => x.id === store.targetId);
    if (!t) return;
    $('#tsum').innerHTML = `<div class="row" style="gap:6px"><span class="tag">${esc(WORLD[t.world_id])}</span><span class="dim">${coord(t.lat, t.lon)}</span></div>
      <p class="muted" style="margin:6px 0">${esc(t.region_type || '')}</p>
      <div class="small">Target data: ${t.completeness.variables_available}/${t.completeness.variables_total} scoring variables
      ${Object.entries(t.completeness.by_class).map(([c, n]) => `${cls(c)} ${n}`).join(' ')}</div>
      <a class="small" href="#/target/${encodeURIComponent(t.id)}">Target profile →</a>`;
  }

  function drawList() {
    const rs = visible();
    $('#rcount').textContent = `${rs.length} of ${result.results.length}`;
    $('#rnote').innerHTML = demoNote(result);
    $('#rlist').innerHTML = rs.length ? rs.map(r => `
      <div class="rankitem ${r.site.id === store.selected ? 'sel' : ''}" role="option" aria-selected="${r.site.id === store.selected}" tabindex="0" data-id="${esc(r.site.id)}">
        <span class="rk">${r.rank ?? '—'}</span>
        <span class="nm">${esc(r.site.name)}<small>${esc(r.site.country || '')} · coverage ${pct(r.coverage)}</small></span>
        <span>${indexCell(r)}</span></div>`).join('') : '<div class="empty small">No candidates match the filters.</div>';
    $$('.rankitem', main).forEach(el => {
      el.addEventListener('click', () => select(el.dataset.id, true));
      el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(el.dataset.id, true); } });
    });
  }

  function drawStatus() {
    const t = result.target;
    const ds = new Set();
    result.results.forEach(r => r.criteria.forEach(c => c.data_class && ds.add(c.data_class)));
    $('#status').innerHTML = `<div class="row between"><div><b>Analysis</b> <span class="status succeeded">complete</span>
      <span class="small muted">${result.n_scored} scored · ${result.n_insufficient} insufficient data · engine ${esc(result.engine_version)} · profile “${esc(result.profile_name)}”</span></div>
      <div class="small">Data classes in use: ${[...ds].map(c => cls(c)).join(' ') || '<span class="dim">none</span>'}</div></div>
      <p class="small dim" style="margin:6px 0 0">Index = weight-normalised mean of available criterion similarities × 100. Results below ${pct(result.thresholds.min_coverage)} weight coverage or with fewer than ${result.thresholds.min_criteria} criteria are not scored. Target: ${esc(t.name)}.</p>`;
  }

  function drawDetail() {
    const r = result.results.find(x => x.site.id === store.selected);
    const el = $('#detail');
    if (!r) { el.innerHTML = '<div class="empty small">Select a candidate on the map or in the ranking to see its evidence.</div>'; return; }
    const inCmp = store.compare.includes(r.site.id);
    el.innerHTML = `
      <div class="row between"><div><h2 style="margin:0">${esc(r.site.name)}</h2><span class="small muted">${esc(r.site.country || '')} · ${coord(r.site.lat, r.site.lon)} · ${r.site.categories.map(c => esc(CAT_LABEL[c] || c)).join(', ')}</span></div>
      <div class="row"><a class="btn sm" href="#/site/${encodeURIComponent(r.site.id)}">Full profile</a><button class="btn sm" id="cmpbtn">${inCmp ? '✓ In comparison' : '+ Compare'}</button></div></div>
      <hr class="sep">${AS.summary(r)}<hr class="sep">${AS.chart(r)}<hr class="sep">${AS.evidence(r, names)}
      <p class="small dim" style="margin-top:10px">Assessment <code>${esc((r.assessment_id || '').slice(0, 12))}</code> · input hash <code>${esc(r.input_hash.slice(0, 12))}</code> — re-running with the same data and weights reproduces this result.</p>`;
    bindTips(el);
    $('#cmpbtn').addEventListener('click', () => {
      if (!toggleCompare(r.site.id)) toast('The comparison holds up to 3 sites. Remove one first.', true);
      drawDetail();
    });
  }

  function select(id, pan) {
    set({ selected: id });
    m.setResults(visible(), id);
    if (pan) m.focus(id);
    drawList();
    drawDetail();
    $(`.rankitem[data-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: 'nearest' });
  }

  async function run() {
    $('#status').innerHTML = '<span class="status running">running</span> <span class="small muted">Scoring candidates…</span>';
    try {
      result = await api.rank(analysisBody());
    } catch (e) {
      $('#status').innerHTML = errorBox(e, 'Analysis');
      return;
    }
    if (!result.results.find(r => r.site.id === store.selected)) {
      const first = result.results.find(r => r.status === 'scored') || result.results[0];
      set({ selected: first ? first.site.id : null });
    }
    drawTarget(); drawStatus(); drawList(); drawDetail();
    m.setResults(visible(), store.selected);
  }

  $('#tsel').addEventListener('change', e => { set({ targetId: e.target.value }); run(); });
  bindWeights(main, vocab, run);
  $('#fq').addEventListener('input', e => { filters.q = e.target.value.trim(); drawList(); m.setResults(visible(), store.selected); });
  $('#fcat').addEventListener('change', e => { filters.cat = e.target.value; drawList(); m.setResults(visible(), store.selected); });
  $('#fins').addEventListener('change', e => { filters.hideInsufficient = e.target.checked; drawList(); m.setResults(visible(), store.selected); });
  $('#csvbtn').addEventListener('click', () => {
    const q = new URLSearchParams({ target_id: store.targetId, include_demo: String(store.includeDemo) });
    if (store.weights) q.set('weights', JSON.stringify(store.weights)); else q.set('profile', store.profile);
    location.href = `/api/export/candidates.csv?${q}`;
  });
  await run();
  // No onRevision hook: on a data revision the router re-renders this page, so
  // newly imported targets, sites and measurements all appear.
  return { destroy() { m.map.remove(); } };
}
