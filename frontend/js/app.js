// EarthTwin SPA shell: hash router, mode indicator, automatic refresh on data revision.
import * as api from './api.js';
import { store, subscribe } from './store.js';
import { $, $$, esc, errorBox } from './ui.js';

const routes = [
  [/^\/?$/, 'home'], [/^\/explore$/, 'explore'], [/^\/targets(?:\/(moon|mars))?$/, 'targets'], [/^\/target\/([^/]+)$/, 'target'],
  [/^\/catalogue$/, 'catalogue'], [/^\/site\/([^/]+)$/, 'site'], [/^\/compare$/, 'compare'], [/^\/data(?:\/(\w+))?$/, 'data'],
  [/^\/dataset\/([^/]+)$/, 'dataset'], [/^\/methodology$/, 'methodology'], [/^\/reports$/, 'reports'], [/^\/about$/, 'about'],
];
const NAV_OF = { target: 'targets', site: 'catalogue', dataset: 'data' };
const TITLES = { home: 'Earth analogs for the Moon and Mars', explore: 'Explorer', targets: 'Moon & Mars targets', target: 'Target region',
  catalogue: 'Earth analog catalogue', site: 'Earth site', compare: 'Comparison laboratory', data: 'Data Center', dataset: 'Dataset',
  methodology: 'Methodology & data sources', reports: 'Reports & exports', about: 'About' };

let current = null;

function parseHash() {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, qs] = raw.split('?');
  for (const [re, name] of routes) {
    const m = path.match(re);
    if (m) return { name, args: m.slice(1).map(x => (x === undefined ? undefined : decodeURIComponent(x))), query: new URLSearchParams(qs || '') };
  }
  return { name: 'home', args: [], query: new URLSearchParams() };
}

async function render(keepScroll = false) {
  const r = parseHash();
  const main = $('#main');
  const y = window.scrollY;
  if (current && current.destroy) { try { current.destroy(); } catch { /* ignore */ } }
  current = null;
  $$('#nav a').forEach(a => a.classList.toggle('on', a.dataset.nav === (NAV_OF[r.name] || r.name)));
  document.title = `${TITLES[r.name] || 'EarthTwin'} · EarthTwin`;
  try {
    const mod = await import(`./pages/${r.name}.js`);
    main.innerHTML = '';
    current = (await mod.render(main, r.args, r.query)) || {};
  } catch (e) {
    console.error(e);
    main.innerHTML = errorBox(e, TITLES[r.name] || 'Page');
  }
  if (keepScroll) window.scrollTo(0, y); else { window.scrollTo(0, 0); }
}

function updateMode(st) {
  if (!st) return;
  const b = $('#modebadge');
  const label = { demo: 'DEMO DATA MODE', mixed: 'MIXED: verified + demo', verified: 'VERIFIED DATA', empty: 'NO ACTIVE DATA' }[st.mode] || st.mode;
  b.className = 'modebadge ' + st.mode;
  b.textContent = label;
  b.title = `${st.datasets_active} active datasets · ${st.sites} Earth sites · ${st.targets} target regions · revision ${st.revision}`;
  $('#demobar').hidden = !(st.demo_active && store.includeDemo);
}

function updateCompare() {
  const c = $('#cmpcount');
  c.hidden = !store.compare.length;
  c.textContent = store.compare.length;
}

window.addEventListener('hashchange', () => { $('#nav').classList.remove('open'); render(); });
$('#navtoggle').addEventListener('click', e => {
  const o = $('#nav').classList.toggle('open');
  e.currentTarget.setAttribute('aria-expanded', String(o));
});
subscribe(() => { updateCompare(); updateMode(api.state()); });
api.onRevision(st => {
  updateMode(st);
  // Data changed (import, activation, edit): refresh the current view in place.
  if (current && current.onRevision) current.onRevision(st);
  else render(true);
});
updateCompare();
api.startPolling();
api.poll().then(updateMode);
render();

export function rerender() { return render(true); }
window.addEventListener('error', e => console.error(esc(e.message)));
