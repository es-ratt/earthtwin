import * as api from '../api.js';
import { bindTips, compareDots, contributionBars, FAMILY_LEGEND, SERIES } from '../charts.js';
import { bindWeights, demoNote, loadCommon, targetSelect, weightsPanel } from '../components.js';
import { analysisBody, analysisQuery, set, store, toggleCompare } from '../store.js';
import { $, $$, esc, cls, indexCell, meter, pct, toast, value } from '../ui.js';

export async function render(main) {
  const { vocab, targets } = await loadCommon();
  const sites = await api.get('/api/sites');
  const names = Object.fromEntries(vocab.criteria.map(c => [c.key, c.name]));
  main.innerHTML = `
  <div class="phead"><div><h1 style="font-size:1.7rem">Comparison laboratory</h1>
    <p>Compare up to three Earth candidates against the same target region, criterion by criterion. All values come from the active datasets; missing data are shown as gaps, never filled.</p></div>
    <div class="row noprint"><button class="btn sm" id="xcsv">Export comparison CSV</button><button class="btn sm" id="xpdf">PDF report</button></div></div>
  <div class="grid" style="grid-template-columns:300px minmax(0,1fr);align-items:start">
    <aside class="card stack">${targetSelect(targets)}
      <div><h4>Sites in comparison</h4><div id="chips" class="stack"></div>
        <label class="field" style="margin-top:8px"><span>Add a site</span><select id="addsel"></select></label></div>
      <hr class="sep">${weightsPanel(vocab)}</aside>
    <section id="out" class="stack" style="min-width:0"></section>
  </div>`;

  function chips() {
    $('#chips').innerHTML = store.compare.length ? store.compare.map((id, i) => {
      const s = sites.find(x => x.id === id);
      return `<div class="row between" style="gap:6px"><span><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${SERIES[i]};margin-right:6px"></i>${esc(s ? s.name : id)}</span>
        <button class="btn sm" data-rm="${esc(id)}" aria-label="Remove ${esc(s ? s.name : id)}">✕</button></div>`;
    }).join('') : '<p class="small dim">No sites selected.</p>';
    $('#addsel').innerHTML = `<option value="">${store.compare.length >= 3 ? 'Maximum of 3 reached' : 'Choose…'}</option>` +
      sites.filter(s => !store.compare.includes(s.id)).map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join('');
    $('#addsel').disabled = store.compare.length >= 3;
    $$('[data-rm]', main).forEach(b => b.addEventListener('click', () => { toggleCompare(b.dataset.rm); chips(); run(); }));
  }

  async function run() {
    const out = $('#out');
    const ids = store.compare.filter(id => sites.find(s => s.id === id));
    if (ids.length !== store.compare.length) set({ compare: ids });
    if (ids.length < 2) {
      out.innerHTML = `<div class="empty"><h3>Select at least two sites</h3><p>Add sites from the list on the left, the <a href="#/catalogue">catalogue</a> or the <a href="#/explore">Explorer</a>.</p>
        <p class="small">Suggestion: compare the current top candidates.</p><button class="btn" id="suggest">Use top 3 for this target</button></div>`;
      $('#suggest').addEventListener('click', async () => {
        const res = await api.rank(analysisBody());
        set({ compare: res.results.filter(r => r.status === 'scored').slice(0, 3).map(r => r.site.id) });
        chips(); run();
      });
      return;
    }
    out.innerHTML = '<p class="muted">Comparing…</p>';
    let res, target;
    try {
      [res, target] = await Promise.all([api.rank(analysisBody({ site_ids: ids })), api.get(`/api/targets/${encodeURIComponent(store.targetId)}?include_demo=${store.includeDemo}`)]);
    } catch (e) { out.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; return; }
    const rs = ids.map(id => res.results.find(r => r.site.id === id));
    const weighted = rs[0].criteria.filter(c => c.weight > 0);
    const legend = `<div class="legend">${rs.map((r, i) => `<span><i style="background:${SERIES[i]}"></i>${esc(r.site.name)}</span>`).join('')}<span><i style="background:transparent;border:1.5px dashed var(--muted)"></i>no data</span></div>`;
    out.innerHTML = `
      ${demoNote(res)}
      <div class="card"><h3>Summary — ${esc(res.target.name)}</h3><p class="small muted">Profile “${esc(res.profile_name)}” · engine ${esc(res.engine_version)}</p>
      <div class="tablewrap"><table><thead><tr><th></th>${rs.map((r, i) => `<th><i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${SERIES[i]};margin-right:6px"></i><a href="#/site/${encodeURIComponent(r.site.id)}">${esc(r.site.name)}</a></th>`).join('')}</tr></thead><tbody>
        <tr><td>Similarity index</td>${rs.map(r => `<td>${indexCell(r)}</td>`).join('')}</tr>
        <tr><td>Rank among all candidates</td>${rs.map(r => `<td>${r.rank ?? '—'}</td>`).join('')}</tr>
        <tr><td>Weight coverage</td>${rs.map(r => `<td>${pct(r.coverage)} <div style="width:90px;display:inline-block;vertical-align:middle">${meter(r.coverage, true)}</div></td>`).join('')}</tr>
        <tr><td>Criteria with data</td>${rs.map(r => `<td>${r.n_criteria_used} / ${r.n_criteria_weighted}</td>`).join('')}</tr>
        <tr><td>Lowest data class</td>${rs.map(r => `<td>${cls(r.lowest_data_class)}</td>`).join('')}</tr>
        <tr><td>Major similarities</td>${rs.map(r => `<td class="small">${r.strengths.map(k => esc(names[k])).join(', ') || '<span class="dim">none ≥ 0.8</span>'}</td>`).join('')}</tr>
        <tr><td>Major mismatches</td>${rs.map(r => `<td class="small">${r.mismatches.map(k => esc(names[k])).join(', ') || '<span class="dim">none &lt; 0.4</span>'}</td>`).join('')}</tr>
        <tr><td>Missing (not counted)</td>${rs.map(r => `<td class="small">${r.missing.map(k => esc(names[k])).join(', ') || '<span class="dim">none</span>'}</td>`).join('')}</tr>
      </tbody></table></div></div>

      <div class="card"><h3>Criterion similarity</h3>${legend}<div class="chart">${compareDots(rs)}</div>
        <p class="small dim">Each dot is the similarity (0–1) between the site's value and the target's value for that criterion. Hover for the underlying difference.</p></div>

      <div class="card"><h3>What drives each index</h3>
        <div class="legend">${FAMILY_LEGEND.map(([f, c]) => `<span><i style="background:${c};border-radius:2px"></i>${f}</span>`).join('')}</div>
        <div class="chart">${contributionBars(rs)}</div><p class="small dim">Index points contributed by each criterion family (sum = index).</p></div>

      <div class="card"><h3>Terrain &amp; environmental metrics</h3><div class="tablewrap"><table>
        <thead><tr><th>Criterion</th><th>Target</th>${rs.map(r => `<th>${esc(r.site.name)}</th>`).join('')}</tr></thead><tbody>
        ${weighted.map(c => `<tr><td>${esc(c.name)} <span class="dim small">w ${c.weight}</span></td>
          <td>${c.method === 'earth_attribute' ? '<span class="dim">Earth-only</span>' : value(c.target_value, c.target_unit)} ${c.target_class ? cls(c.target_class) : ''}</td>
          ${rs.map(r => { const x = r.criteria.find(z => z.criterion === c.criterion); return `<td>${value(x.site_value, x.site_unit)} ${x.site_class ? cls(x.site_class) : ''}<br><span class="small dim">sim ${x.similarity === null ? '—' : x.similarity.toFixed(2)}</span></td>`; }).join('')}</tr>`).join('')}
        </tbody></table></div></div>

      <div class="card"><h3>Sources</h3><p class="small muted">Datasets contributing values to this comparison:</p>
        <ul class="small">${[...new Set([...target.observations.map(o => o.dataset_name + '|' + o.dataset_id)])].map(x => { const [n, id] = x.split('|'); return `<li>Target: <a href="#/dataset/${encodeURIComponent(id)}">${esc(n)}</a></li>`; }).join('')}
        ${[...new Set(rs.flatMap(r => r.criteria.map(c => c.site_observation ? 'x' : null)).filter(Boolean))].length ? '<li>Earth sites: see each <a href="#/catalogue">site profile</a> for per-value sources.</li>' : ''}</ul>
        <p class="small"><a href="#/methodology">Methodology &amp; full citation list →</a></p></div>`;
    bindTips(out);
  }

  $('#addsel').addEventListener('change', e => { if (e.target.value) { toggleCompare(e.target.value); chips(); run(); } });
  $('#tsel').addEventListener('change', e => { set({ targetId: e.target.value }); run(); });
  bindWeights(main, vocab, run);
  const q = () => { const p = analysisQuery(); p.set('site_ids', store.compare.join(',')); return p; };
  $('#xcsv').addEventListener('click', () => { if (store.compare.length < 2) return toast('Select at least two sites.', true); location.href = `/api/export/comparison.csv?${q()}`; });
  $('#xpdf').addEventListener('click', () => { const p = analysisQuery(); p.set('site_ids', store.compare.join(',')); location.href = `/api/export/report.pdf?${p}`; });
  chips();
  await run();
}
