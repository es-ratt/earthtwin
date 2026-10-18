// Shared data service: every page reads through here, so a data revision bump
// (new import, activation change) invalidates caches and refreshes all views.
const cache = new Map();
const listeners = new Set();
let revision = null;
let lastState = null;

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function parse(res) {
  const ct = res.headers.get('content-type') || '';
  const body = ct.includes('json') ? await res.json().catch(() => null) : await res.text();
  if (!res.ok) {
    let msg = body && body.detail ? body.detail : `Request failed (${res.status})`;
    if (Array.isArray(msg)) msg = msg.map(d => `${(d.loc || []).join('.')}: ${d.msg}`).join('; ');
    throw new ApiError(msg, res.status);
  }
  return body;
}

export async function get(path, { fresh = false } = {}) {
  if (!fresh && cache.has(path)) return cache.get(path);
  const p = fetch(path, { headers: { Accept: 'application/json' } }).then(parse);
  cache.set(path, p);
  p.catch(() => cache.delete(path));
  return p;
}

export const admin = {
  get token() { try { return sessionStorage.getItem('et-admin') || ''; } catch { return ''; } },
  set token(v) { try { v ? sessionStorage.setItem('et-admin', v) : sessionStorage.removeItem('et-admin'); } catch { /* storage blocked */ } },
};

function headers(json = true) {
  const h = { Accept: 'application/json' };
  if (json) h['Content-Type'] = 'application/json';
  if (admin.token) h['X-Admin-Token'] = admin.token;
  return h;
}

export async function send(method, path, body) {
  const res = await fetch(path, { method, headers: headers(body !== undefined), body: body === undefined ? undefined : JSON.stringify(body) });
  return parse(res);
}
export const post = (p, b) => send('POST', p, b);
export const put = (p, b) => send('PUT', p, b);
export const patch = (p, b) => send('PATCH', p, b);
export const del = (p) => send('DELETE', p);

export async function upload(file, kind) {
  const fd = new FormData();
  fd.append('file', file);
  if (kind) fd.append('kind', kind);
  const res = await fetch('/api/imports', { method: 'POST', headers: headers(false), body: fd });
  return parse(res);
}

// Analysis results are cached per request body and revision.
export async function rank(body) {
  const key = 'rank:' + JSON.stringify(body);
  if (cache.has(key)) return cache.get(key);
  const p = post('/api/analysis/rank', body);
  cache.set(key, p);
  p.catch(() => cache.delete(key));
  return p;
}

export function onRevision(fn) { listeners.add(fn); return () => listeners.delete(fn); }
export function state() { return lastState; }

export async function poll() {
  try {
    const st = await fetch('/api/state').then(parse);
    lastState = st;
    if (revision !== null && st.revision !== revision) {
      cache.clear();
      revision = st.revision;
      listeners.forEach(fn => { try { fn(st); } catch (e) { console.error(e); } });
    }
    revision = st.revision;
    return st;
  } catch (e) {
    return null;
  }
}

export function invalidate() { cache.clear(); return poll(); }

export function startPolling(ms = 4000) {
  poll();
  setInterval(() => { if (!document.hidden) poll(); }, ms);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
}
