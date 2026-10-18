// Per-viewer analysis settings (selected target, weighting, compare set).
// Stored in localStorage purely as a convenience; the app works without it.
const KEY = 'earthtwin-state-v1';
const defaults = { targetId: 'lunar-south-pole-shackleton', profile: 'general', weights: null, includeDemo: true, compare: [], selected: null };

function load() {
  try { return { ...defaults, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch { return { ...defaults }; }
}
export const store = load();
const subs = new Set();

export function set(patch) {
  Object.assign(store, patch);
  try { localStorage.setItem(KEY, JSON.stringify(store)); } catch { /* storage blocked */ }
  subs.forEach(fn => fn(store));
}
export function subscribe(fn) { subs.add(fn); return () => subs.delete(fn); }

export function analysisBody(extra = {}) {
  const b = { target_id: store.targetId, include_demo: store.includeDemo };
  if (store.weights) b.weights = store.weights; else b.profile = store.profile;
  return { ...b, ...extra };
}
export function analysisQuery() {
  const q = new URLSearchParams({ target_id: store.targetId, include_demo: String(store.includeDemo) });
  if (store.weights) q.set('weights', JSON.stringify(store.weights)); else q.set('profile', store.profile);
  return q;
}

export function toggleCompare(id) {
  const c = [...store.compare];
  const i = c.indexOf(id);
  if (i >= 0) c.splice(i, 1);
  else if (c.length < 3) c.push(id);
  else return false;
  set({ compare: c });
  return true;
}
