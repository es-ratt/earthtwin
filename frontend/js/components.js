// Reusable analysis controls shared by Explorer, Compare and Reports.
import * as api from './api.js';
import { store, set } from './store.js';
import { $, $$, esc } from './ui.js';

export async function loadCommon() {
  const [vocab, targets] = await Promise.all([api.get('/api/vocabulary'), api.get('/api/targets')]);
  if (!targets.find(t => t.id === store.targetId) && targets.length) set({ targetId: targets[0].id });
  return { vocab, targets };
}

export function targetSelect(targets, id = 'tsel') {
  const grp = w => targets.filter(t => t.world_id === w).map(t => `<option value="${esc(t.id)}" ${t.id === store.targetId ? 'selected' : ''}>${esc(t.name)}</option>`).join('');
  return `<label class="field"><span>Target region</span><select id="${id}"><optgroup label="Moon">${grp('moon')}</optgroup><optgroup label="Mars">${grp('mars')}</optgroup></select></label>`;
}

export function currentWeights(vocab) {
  return store.weights || vocab.profiles[store.profile]?.weights || vocab.profiles.general.weights;
}

export function weightsPanel(vocab, { open = false } = {}) {
  const w = currentWeights(vocab);
  const fams = ['terrain', 'geology', 'environment', 'resources', 'operational'];
  const crit = vocab.criteria;
  return `
  <label class="field"><span>Weighting profile</span>
    <select id="psel">${Object.entries(vocab.profiles).map(([k, p]) => `<option value="${esc(k)}" ${!store.weights && store.profile === k ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}
      <option value="custom" ${store.weights ? 'selected' : ''}>Custom weights</option></select></label>
  <p class="small muted" id="pdesc" style="margin:6px 0 8px">${store.weights ? 'Custom weights — the index is a weight-normalised mean, so weights are relative.' : esc(vocab.profiles[store.profile]?.description || '')}</p>
  <details class="weights" ${open ? 'open' : ''}><summary class="small" style="cursor:pointer;color:var(--muted)">Criterion weights</summary>
  <div style="margin-top:8px">${fams.map(f => `<h4 style="margin:10px 0 4px">${f}</h4>` + crit.filter(c => c.family === f).map(c =>
    `<label title="${esc(c.description)}"><span>${esc(c.name)}${c.family === 'operational' ? ' <span class="dim">(Earth-only)</span>' : ''}</span><b data-wv="${esc(c.key)}">${w[c.key] ?? 0}</b>
     <input type="range" min="0" max="40" step="1" value="${w[c.key] ?? 0}" data-w="${esc(c.key)}" aria-label="${esc(c.name)} weight"></label>`).join('')).join('')}
  <button class="btn sm" id="wreset" type="button">Reset to profile</button></div></details>
  <label class="check" style="margin-top:10px"><input type="checkbox" id="demotog" ${store.includeDemo ? 'checked' : ''}> Include demonstration data</label>`;
}

export function bindWeights(root, vocab, onChange) {
  let t;
  const fire = () => { clearTimeout(t); t = setTimeout(onChange, 180); };
  $('#psel', root)?.addEventListener('change', e => {
    const v = e.target.value;
    if (v === 'custom') set({ weights: { ...currentWeights(vocab) } });
    else set({ profile: v, weights: null });
    onChange(true);
  });
  $$('[data-w]', root).forEach(inp => inp.addEventListener('input', e => {
    const w = { ...currentWeights(vocab), [e.target.dataset.w]: Number(e.target.value) };
    set({ weights: w });
    $(`[data-wv="${e.target.dataset.w}"]`, root).textContent = e.target.value;
    const ps = $('#psel', root); if (ps) ps.value = 'custom';
    $('#pdesc', root).textContent = 'Custom weights — the index is a weight-normalised mean, so weights are relative.';
    fire();
  }));
  $('#wreset', root)?.addEventListener('click', () => { set({ weights: null }); onChange(true); });
  $('#demotog', root)?.addEventListener('change', e => { set({ includeDemo: e.target.checked }); onChange(true); });
}

export function demoNote(result) {
  if (!result || !result.is_demo) return '';
  return `<div class="notice warn small"><b>DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT.</b> One or more inputs are illustrative placeholder values.</div>`;
}
