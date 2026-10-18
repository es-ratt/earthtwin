import * as api from '../api.js';
import { earthMap } from '../maps.js';
import { store, toggleCompare } from '../store.js';
import { $, $$, esc, cls, coord, meter, CAT_LABEL, toast } from '../ui.js';

export async function render(main, _a, query) {
  const [sites, vocab] = await Promise.all([api.get(`/api/sites?include_demo=${store.includeDemo}`), api.get('/api/vocabulary')]);
  const f = { q: query.get('q') || '', cat: query.get('category') || '', sort: 'name' };
  main.innerHTML = `
  <div class="phead"><div><h1 style="font-size:1.7rem">Earth analog catalogue</h1>
    <p>Terrestrial environments that may share conditions with lunar or Martian targets. Each record shows which measurements are available and where they come from. The catalogue grows automatically when site records are imported.</p></div>
    <a class="btn sm" href="#/data">Import sites</a></div>
  <div class="card row" style="margin-bottom:14px">
    <label class="field" style="flex:1;min-width:200px"><span>Search</span><input id="cq" type="search" value="${esc(f.q)}" placeholder="name, country, description"></label>
    <label class="field"><span>Category</span><select id="ccat"><option value="">All</option>${Object.entries(vocab.site_categories).map(([k, v]) => `<option value="${esc(k)}" ${f.cat === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select></label>
    <label class="field"><span>Sort</span><select id="csort"><option value="name">Name</option><option value="data">Data completeness</option><option value="lat">Latitude</option></select></label>
  </div>
  <div class="grid" style="grid-template-columns:minmax(0,1fr) minmax(0,1.2fr)">
    <div class="card mapcard" style="padding:0;overflow:hidden;align-self:start;position:sticky;top:76px"><div id="cmap" style="height:460px"></div></div>
    <div id="clist" class="stack"></div>
  </div>`;
  const m = await earthMap($('#cmap'), { compact: true });

  function rows() {
    const q = f.q.toLowerCase();
    let r = sites.filter(s => (!f.cat || s.categories.includes(f.cat)) &&
      (!q || `${s.name} ${s.country} ${s.region} ${s.description}`.toLowerCase().includes(q)));
    if (f.sort === 'data') r.sort((a, b) => b.completeness.fraction - a.completeness.fraction);
    else if (f.sort === 'lat') r.sort((a, b) => b.lat - a.lat);
    return r;
  }
  function draw() {
    const r = rows();
    m.setSites(r, id => { location.hash = `#/site/${encodeURIComponent(id)}`; });
    $('#clist').innerHTML = r.length ? r.map(s => `
      <article class="card">
        <div class="row between"><div><h3 style="margin:0"><a href="#/site/${encodeURIComponent(s.id)}" style="color:var(--text)">${esc(s.name)}</a></h3>
          <span class="small muted">${esc([s.region, s.country].filter(Boolean).join(', '))} · ${coord(s.lat, s.lon)}</span></div>
          <button class="btn sm" data-cmp="${esc(s.id)}">${store.compare.includes(s.id) ? '✓ Comparing' : '+ Compare'}</button></div>
        <div class="row" style="margin:6px 0">${s.categories.map(c => `<span class="tag">${esc(CAT_LABEL[c] || c)}</span>`).join('')} ${s.terrain_type ? `<span class="small dim">${esc(s.terrain_type)}</span>` : ''}</div>
        <p class="small" style="margin-bottom:8px">${esc(s.description || '')}</p>
        <div class="row small" style="gap:14px"><span style="width:140px">${meter(s.completeness.fraction, true)}</span>
          <span class="muted">${s.completeness.variables_available}/${s.completeness.variables_total} scoring variables</span>
          ${Object.entries(s.completeness.by_class).map(([c, n]) => `${cls(c)} <span class="dim">${n}</span>`).join(' ')}
          ${!Object.keys(s.completeness.by_class).length ? '<span class="cls missing">no measurements</span>' : ''}</div>
      </article>`).join('') : '<div class="empty"><h3>No sites match</h3>Adjust the filters, or import site records in the Data Center.</div>';
    $$('[data-cmp]', main).forEach(b => b.addEventListener('click', () => {
      if (!toggleCompare(b.dataset.cmp)) return toast('The comparison holds up to 3 sites.', true);
      draw();
    }));
  }
  $('#cq').addEventListener('input', e => { f.q = e.target.value.trim(); draw(); });
  $('#ccat').addEventListener('change', e => { f.cat = e.target.value; draw(); });
  $('#csort').addEventListener('change', e => { f.sort = e.target.value; draw(); });
  draw();
  return { destroy() { m.map.remove(); } };
}
