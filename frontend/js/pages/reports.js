import * as api from '../api.js';
import { bindWeights, loadCommon, targetSelect, weightsPanel } from '../components.js';
import { analysisQuery, set, store } from '../store.js';
import { $, esc, fmtDate } from '../ui.js';

export async function render(main) {
  const { vocab, targets } = await loadCommon();
  const sites = await api.get('/api/sites');
  const hist = await api.get('/api/exports', { fresh: true });
  const nm = id => sites.find(s => s.id === id)?.name || id;
  main.innerHTML = `
  <div class="phead"><div><h1 style="font-size:1.7rem">Reports &amp; exports</h1>
    <p>Exports are generated on the server from the same assessments the website shows, with the target, scores, methodology, criterion-level results, sources, differences, limitations and generation date. Results based on demonstration values are marked <b>DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT</b>.</p></div></div>
  <div class="grid" style="grid-template-columns:320px minmax(0,1fr);align-items:start">
    <aside class="card stack">${targetSelect(targets)}${weightsPanel(vocab)}</aside>
    <div class="stack">
      <div class="card"><h3>Candidate list (CSV)</h3><p class="small muted">All candidates ranked for the selected target with index, coverage, data class, per-criterion similarities, assessment IDs and input hashes.</p><button class="btn primary" id="x1">Download candidates.csv</button></div>
      <div class="card"><h3>Comparison results (CSV)</h3><p class="small muted">Long-format table: every criterion for every compared site, with both values, units, data classes, similarity and contribution.</p>
        <p class="small">Sites: ${store.compare.length ? store.compare.map(id => esc(nm(id))).join(', ') : '<span class="dim">none selected — choose sites in the <a href="#/compare">Comparison lab</a></span>'}</p>
        <button class="btn primary" id="x2" ${store.compare.length < 2 ? 'disabled' : ''}>Download comparison.csv</button></div>
      <div class="card"><h3>Scientific comparison report (PDF)</h3><p class="small muted">Target summary and measurements, method, weights, ranking, criterion-level tables for the compared sites (or the top 3), important differences, missing data, data sources, citations and limitations.</p>
        <button class="btn primary" id="x3">Generate PDF report</button></div>
      <div class="card"><h3>Recent exports</h3>${hist.length ? `<table><tbody>${hist.slice(0, 12).map(h => `<tr><td>${esc(h.kind.replace('_', ' '))}</td><td>${esc(h.target_region_id || '')}</td><td class="small dim">${fmtDate(h.created_at)}</td></tr>`).join('')}</tbody></table>` : '<p class="small dim">No exports yet.</p>'}</div>
    </div></div>`;
  $('#tsel').addEventListener('change', e => set({ targetId: e.target.value }));
  bindWeights(main, vocab, () => {});
  $('#x1').addEventListener('click', () => { location.href = `/api/export/candidates.csv?${analysisQuery()}`; });
  $('#x2').addEventListener('click', () => { const q = analysisQuery(); q.set('site_ids', store.compare.join(',')); location.href = `/api/export/comparison.csv?${q}`; });
  $('#x3').addEventListener('click', () => { const q = analysisQuery(); if (store.compare.length) q.set('site_ids', store.compare.join(',')); location.href = `/api/export/report.pdf?${q}`; });
}
