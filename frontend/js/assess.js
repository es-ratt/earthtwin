// Rendering of a single SimilarityAssessment (shared by Explorer and site pages).
import { criterionBars } from './charts.js';
import { cls, esc, indexCell, meter, num, pct, value } from './ui.js';

export function summary(r) {
  const scored = r.status === 'scored';
  return `
  <div class="grid g3" style="gap:10px">
    <div class="kpi"><span class="l">Prototype similarity index</span><span class="v">${scored ? num(r.score, 1) : '<span class="insuff" style="font-size:1rem">Insufficient data</span>'}</span>
      ${scored ? meter(r.score / 100, false, 'index ' + num(r.score, 1)) : `<span class="small dim">${esc(r.reason)}</span>`}</div>
    <div class="kpi"><span class="l">Weight coverage (data available)</span><span class="v">${pct(r.coverage)}</span>${meter(r.coverage, true)}</div>
    <div class="kpi"><span class="l">Criteria used · lowest data class</span><span class="v" style="font-size:1.25rem">${r.n_criteria_used} / ${r.n_criteria_weighted}</span><span>${cls(r.lowest_data_class)}</span></div>
  </div>`;
}

export function evidence(r, names) {
  const nm = k => esc(names[k] || k);
  const by = Object.fromEntries(r.criteria.map(c => [c.criterion, c]));
  const li = (k, extra = '') => `<li><b>${nm(k)}</b> <span class="small muted">${esc(by[k]?.detail || '')}</span>${extra}</li>`;
  return `
  <div class="grid g3" style="gap:12px">
    <div><h4>Supporting similarities</h4>${r.strengths.length ? `<ul class="small">${r.strengths.map(k => li(k)).join('')}</ul>` : '<p class="small dim">No criterion ≥ 0.8.</p>'}</div>
    <div><h4>Important differences</h4>${r.mismatches.length ? `<ul class="small">${r.mismatches.map(k => li(k)).join('')}</ul>` : '<p class="small dim">No criterion below 0.4.</p>'}</div>
    <div><h4>Missing data (not counted)</h4>${r.missing.length ? `<ul class="small">${r.missing.map(k => `<li>${nm(k)} — <span class="dim">${esc(by[k]?.status.replace('_', ' '))}</span></li>`).join('')}</ul>` : '<p class="small dim">All weighted criteria had data.</p>'}</div>
  </div>`;
}

export function chart(r) {
  return `<div class="chart">${criterionBars(r.criteria)}</div>
  <p class="small dim">Bar = similarity (0–1) for each weighted criterion; right column = weight · index points contributed. Hatched = no data on one side, excluded from the index.</p>`;
}

export function table(r) {
  return `<div class="tablewrap"><table><thead><tr><th>Criterion</th><th class="num">Weight</th><th>Earth site</th><th>Target</th><th class="num">Similarity</th><th class="num">Points</th><th>Class</th></tr></thead><tbody>
  ${r.criteria.map(c => `<tr${c.weight === 0 ? ' class="dim"' : ''}><td>${esc(c.name)}<br><span class="small dim">${esc(c.method)}</span></td><td class="num">${c.weight}</td>
    <td>${value(c.site_value, c.site_unit)}</td><td>${c.method === 'earth_attribute' ? '<span class="dim">n/a (Earth-only)</span>' : value(c.target_value, c.target_unit)}</td>
    <td class="num">${c.similarity === null ? '<span class="dim">—</span>' : c.similarity.toFixed(2)}</td><td class="num">${c.contribution === null ? '' : c.contribution.toFixed(1)}</td>
    <td>${c.similarity === null ? `<span class="small dim">${esc(c.status.replace('_', ' '))}</span>` : cls(c.data_class)}</td></tr>`).join('')}
  </tbody></table></div>`;
}

export { indexCell };
