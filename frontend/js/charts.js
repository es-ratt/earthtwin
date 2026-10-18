// Inline-SVG charts. Every chart plots only values returned by the analysis API
// (criterion similarities computed from imported or labelled demo data); no
// value is synthesised here. Each chart has a table equivalent on its page.
import { esc, num } from './ui.js';

export const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)'];
// Categorical slots 4–8 (validated adjacent-pair CVD-safe on the dark surface); slots 1–3 are reserved for site identity.
export const FAMILY_LEGEND = [['terrain', '#c98500'], ['geology', '#d55181'], ['environment', '#008300'], ['resources', '#9085e9'], ['operational', '#e66767']];
export const SEQ = ['var(--seq-1)', 'var(--seq-2)', 'var(--seq-3)', 'var(--seq-4)', 'var(--seq-5)'];
export const SEQ_HEX = ['#1c5cab', '#2a78d6', '#5598e7', '#86b6ef', '#cde2fb'];

export function scoreColor(score) {
  if (score === null || score === undefined) return null;
  return SEQ_HEX[Math.max(0, Math.min(4, Math.floor(score / 20)))];
}

let tipEl;
function tip() {
  if (!tipEl) { tipEl = document.createElement('div'); tipEl.className = 'charttip'; tipEl.hidden = true; document.body.appendChild(tipEl); }
  return tipEl;
}
export function bindTips(root) {
  root.querySelectorAll('[data-tip]').forEach(n => {
    const show = e => {
      const t = tip();
      t.innerHTML = n.getAttribute('data-tip');
      t.hidden = false;
      const x = (e.clientX ?? (n.getBoundingClientRect().left + 20));
      const y = (e.clientY ?? n.getBoundingClientRect().top);
      const w = t.offsetWidth;
      t.style.left = Math.min(window.innerWidth - w - 10, x + 14) + 'px';
      t.style.top = (y + 14) + 'px';
    };
    n.addEventListener('pointermove', show);
    n.addEventListener('pointerenter', show);
    n.addEventListener('focus', show);
    n.addEventListener('pointerleave', () => { tip().hidden = true; });
    n.addEventListener('blur', () => { tip().hidden = true; });
  });
}

const hatchDef = id => `<defs><pattern id="${id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="transparent"/><line x1="0" y1="0" x2="0" y2="6" stroke="var(--line-2)" stroke-width="2"/></pattern></defs>`;

function barPath(x0, y, w, h, r = 4) {
  // square at the baseline, 4px rounded data-end
  if (w <= 0) return '';
  r = Math.min(r, w, h / 2);
  return `M${x0},${y}H${x0 + w - r}Q${x0 + w},${y} ${x0 + w},${y + r}V${y + h - r}Q${x0 + w},${y + h} ${x0 + w - r},${y + h}H${x0}Z`;
}

/** Horizontal bars: similarity (0–1) per weighted criterion; missing criteria hatched. */
export function criterionBars(criteria, { width = 640 } = {}) {
  const rows = criteria.filter(c => c.weight > 0);
  if (!rows.length) return '<p class="muted small">No weighted criteria.</p>';
  const L = 168, R = 92, rowH = 30, bar = 14, top = 22;
  const W = width, plotW = W - L - R, H = top + rows.length * rowH + 8;
  const x = v => L + v * plotW;
  const id = 'h' + Math.random().toString(36).slice(2, 8);
  let s = `<svg viewBox="0 0 ${W} ${H}" style="max-width:${W}px" role="img" aria-label="Similarity per criterion">${hatchDef(id)}`;
  s += `<g class="grid">${[0, .25, .5, .75, 1].map(v => `<line x1="${x(v)}" x2="${x(v)}" y1="${top - 6}" y2="${H - 6}"/><text x="${x(v)}" y="${top - 10}" text-anchor="middle">${v}</text>`).join('')}</g>`;
  s += `<text x="${W - R + 10}" y="${top - 10}">weight · pts</text>`;
  rows.forEach((c, i) => {
    const y = top + i * rowH + (rowH - bar) / 2;
    const cy = y + bar / 2 + 4;
    const tipTxt = `<b>${esc(c.name)}</b>${c.similarity === null ? 'No data on ' + (c.status === 'missing_target' ? 'target' : c.status === 'missing_site' ? 'Earth site' : 'either side') + ' — not counted' : 'Similarity ' + c.similarity.toFixed(2)}<br>${esc(c.detail || '')}<br><span class="muted">weight ${c.weight}${c.contribution !== null ? ' · contributes ' + c.contribution.toFixed(1) + ' pts' : ''}${c.data_class ? ' · ' + esc(c.data_class) : ''}</span>`;
    s += `<g class="rowhover" data-tip="${esc(tipTxt)}" tabindex="0">`;
    s += `<rect class="hit" x="0" y="${top + i * rowH}" width="${W}" height="${rowH}"/>`;
    s += `<text class="lbl" x="${L - 10}" y="${cy}" text-anchor="end">${esc(c.name)}</text>`;
    if (c.similarity === null) {
      s += `<rect x="${L}" y="${y}" width="${plotW}" height="${bar}" fill="url(#${id})" opacity=".6"/><text x="${L + 8}" y="${cy}" class="val" style="fill:var(--dim)">no data</text>`;
    } else {
      const w = Math.max(2, c.similarity * plotW);
      s += `<path class="mark" d="${barPath(L, y, w, bar)}" fill="var(--seq-3)"/>`;
      const inside = w > 44;
      s += `<text class="val" x="${inside ? L + w - 6 : L + w + 6}" y="${cy}" text-anchor="${inside ? 'end' : 'start'}" style="${inside ? 'fill:#04121a' : ''}">${c.similarity.toFixed(2)}</text>`;
    }
    s += `<text x="${W - R + 10}" y="${cy}" class="val" style="fill:var(--muted)">${c.weight}${c.contribution !== null ? ' · ' + c.contribution.toFixed(1) : ''}</text></g>`;
  });
  return s + '</svg>';
}

/** Dot plot: criterion rows × up to 3 sites. */
export function compareDots(results, { width = 760 } = {}) {
  if (!results.length) return '';
  const keys = results[0].criteria.filter(c => c.weight > 0).map(c => c.criterion);
  const names = Object.fromEntries(results[0].criteria.map(c => [c.criterion, c.name]));
  const L = 170, R = 20, rowH = 30, top = 24;
  const W = width, plotW = W - L - R, H = top + keys.length * rowH + 6;
  const x = v => L + v * plotW;
  let s = `<svg viewBox="0 0 ${W} ${H}" style="max-width:${W}px" role="img" aria-label="Criterion similarity by site">`;
  s += `<g class="grid">${[0, .25, .5, .75, 1].map(v => `<line x1="${x(v)}" x2="${x(v)}" y1="${top - 6}" y2="${H - 4}"/><text x="${x(v)}" y="${top - 10}" text-anchor="middle">${v}</text>`).join('')}</g>`;
  keys.forEach((k, i) => {
    const cy = top + i * rowH + rowH / 2;
    s += `<text class="lbl" x="${L - 10}" y="${cy + 4}" text-anchor="end">${esc(names[k])}</text>`;
    s += `<line x1="${L}" x2="${L + plotW}" y1="${cy}" y2="${cy}" stroke="var(--line)"/>`;
    results.forEach((r, j) => {
      const c = r.criteria.find(z => z.criterion === k);
      const off = (j - (results.length - 1) / 2) * 5;
      const t = `<b>${esc(r.site.name)}</b>${esc(names[k])}: ${c.similarity === null ? 'no data (not counted)' : c.similarity.toFixed(2)}<br><span class="muted">${esc(c.detail || '')}</span>`;
      if (c.similarity === null) {
        s += `<g data-tip="${esc(t)}" tabindex="0"><circle cx="${L - 2 + 0}" cy="${cy + off}" r="9" fill="transparent"/><circle cx="${L + 6 + j * 12}" cy="${cy}" r="4" fill="none" stroke="${SERIES[j]}" stroke-width="1.5" stroke-dasharray="2 2"/></g>`;
      } else {
        s += `<g data-tip="${esc(t)}" tabindex="0"><circle cx="${x(c.similarity)}" cy="${cy + off}" r="10" fill="transparent"/><circle cx="${x(c.similarity)}" cy="${cy + off}" r="5" fill="${SERIES[j]}" stroke="var(--surface)" stroke-width="2"/></g>`;
      }
    });
  });
  return s + '</svg>';
}

/** Stacked contribution bars: how many index points each criterion family contributes per site. */
export function contributionBars(results, { width = 760 } = {}) {
  const fam = ['terrain', 'geology', 'environment', 'resources', 'operational'];
  const famColor = Object.fromEntries(FAMILY_LEGEND);
  const L = 170, R = 60, rowH = 34, bar = 16, top = 20;
  const W = width, plotW = W - L - R, H = top + results.length * rowH + 6;
  const x = v => L + (v / 100) * plotW;
  let s = `<svg viewBox="0 0 ${W} ${H}" style="max-width:${W}px" role="img" aria-label="Index points by criterion family">`;
  s += `<g class="grid">${[0, 25, 50, 75, 100].map(v => `<line x1="${x(v)}" x2="${x(v)}" y1="${top - 4}" y2="${H - 4}"/><text x="${x(v)}" y="${top - 8}" text-anchor="middle">${v}</text>`).join('')}</g>`;
  results.forEach((r, i) => {
    const y = top + i * rowH + (rowH - bar) / 2;
    s += `<text class="lbl" x="${L - 10}" y="${y + bar / 2 + 4}" text-anchor="end">${esc(r.site.name)}</text>`;
    if (r.status !== 'scored') {
      s += `<text x="${L + 6}" y="${y + bar / 2 + 4}" style="fill:var(--dim);font-style:italic">Insufficient data — ${esc(r.reason || '')}</text>`;
      return;
    }
    let acc = 0;
    fam.forEach(f => {
      const pts = r.criteria.filter(c => c.family === f && c.contribution !== null).reduce((a, c) => a + c.contribution, 0);
      if (pts <= 0) return;
      const x0 = x(acc), w = Math.max(1, x(acc + pts) - x0 - 2);
      s += `<g data-tip="${esc(`<b>${esc(r.site.name)}</b>${f}: ${pts.toFixed(1)} index points`)}" tabindex="0"><rect x="${x0}" y="${y}" width="${w}" height="${bar}" fill="${famColor[f]}" rx="1"/></g>`;
      acc += pts;
    });
    s += `<text class="val" x="${x(acc) + 6}" y="${y + bar / 2 + 4}">${num(r.score, 1)}</text>`;
  });
  return s + '</svg>';
}

