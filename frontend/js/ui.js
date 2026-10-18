// UI helpers. All dynamic text goes through esc(): imported data are untrusted.
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = v => (v === null || v === undefined ? '' : String(v)).replace(/[&<>"']/g, c => ESC[c]);
export const safeUrl = u => (/^https?:\/\//i.test(String(u || '')) ? esc(u) : '');

export const CLASS_LABEL = { verified: 'verified', derived: 'derived', demo: 'demo', reference: 'reference' };
export function cls(c, title) {
  if (!c) return `<span class="cls missing" title="No data">missing</span>`;
  const t = title || { verified: 'Value from an identified dataset imported by the team', derived: 'Calculated by the EarthTwin pipeline from documented inputs',
    demo: 'Illustrative demonstration value — not a verified scientific result', reference: 'Catalogue / context record without measurements' }[c] || c;
  return `<span class="cls ${esc(c)}" title="${esc(t)}">${esc(CLASS_LABEL[c] || c)}</span>`;
}
export const status = s => `<span class="status ${esc(s)}">${esc((s || '').replace(/_/g, ' '))}</span>`;

export function num(v, d = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const a = Math.abs(v);
  if (a !== 0 && (a >= 100000 || a < 0.01)) return Number(v).toExponential(1);
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: a >= 100 ? 0 : d });
}
export function value(v, unit) {
  if (v === null || v === undefined) return '<span class="dim">—</span>';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (Array.isArray(v)) return v.map(x => `<span class="tag">${esc(x.replace(/_/g, ' '))}</span>`).join(' ');
  if (typeof v === 'number') return `${num(v)}${unit ? ' <span class="dim">' + esc(unit) + '</span>' : ''}`;
  return esc(v);
}
export const pct = v => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`);
export function indexCell(r) {
  if (!r || r.status !== 'scored') return `<span class="insuff" title="${esc(r && r.reason)}">Insufficient data</span>`;
  return `<span class="index">${num(r.score, 1)}</span>`;
}
export function meter(frac, cov = false, label = '') {
  const p = Math.max(0, Math.min(1, frac || 0)) * 100;
  return `<div class="meter${cov ? ' cov' : ''}" role="img" aria-label="${esc(label || Math.round(p) + ' percent')}"><i style="width:${p.toFixed(1)}%"></i></div>`;
}
export function fmtDate(s) {
  if (!s) return '';
  try { return new Date(s).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); } catch { return s; }
}
export const bytes = n => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n > 1024 ? `${(n / 1024).toFixed(0)} KB` : `${n} B`);
export const coord = (lat, lon) => `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? 'E' : 'W'}`;

let toastTimer;
export function toast(msg, err = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast' + (err ? ' err' : '');
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, err ? 7000 : 3500);
}

export function errorBox(e, what = 'This view') {
  return `<div class="notice err"><b>${esc(what)} could not be loaded.</b> ${esc(e && e.message ? e.message : e)}<br><span class="small muted">Is the EarthTwin server running? Try reloading the page.</span></div>`;
}

export const WORLD = { earth: 'Earth', moon: 'Moon', mars: 'Mars' };
export const CAT_LABEL = { arid: 'Arid / desert', volcanic: 'Volcanic', polar: 'Polar / glacial', impact: 'Impact crater', cave: 'Cave / subsurface', highland: 'Highland / rugged', hydrothermal: 'Hydrothermal / acidic' };

export function download(url) {
  // Opens a server-generated export (CSV/PDF) in a way that works without blob URLs.
  const a = document.createElement('a');
  a.href = url;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

const VERIF = { team_verified: 'verified by team', link_checked: 'link checked', unverified: 'not yet verified' };
export function citeList(cits) {
  if (!cits || !cits.length) return '<p class="small dim">No citations recorded.</p>';
  const seen = new Set();
  return `<ul class="small">${cits.filter(c => { const k = c.text + c.url; if (seen.has(k)) return false; seen.add(k); return true; }).map(c => {
    const u = safeUrl(c.url);
    return `<li>${esc(c.text)}${c.doi ? ` doi:<span class="mono">${esc(c.doi)}</span>` : ''} ${u ? `<a href="${u}" target="_blank" rel="noopener">source ↗</a>` : ''}
      <span class="dim">· ${esc(c.kind)} · ${esc(VERIF[c.verification] || c.verification)}</span></li>`;
  }).join('')}</ul>`;
}
