import * as api from '../api.js';
import { $, $$, esc, bytes, cls, fmtDate, safeUrl, status, toast } from '../ui.js';

// Wizard state lives at module level so a background data refresh never loses work in progress.
const W = { step: 1, session: null, kind: null, mapping: null, metadata: null, job: null, prefill: null };
let formats = null, vocab = null;
const TABS = [['datasets', 'Datasets'], ['import', 'Import data'], ['history', 'Import history'], ['formats', 'Formats & templates'], ['providers', 'Providers']];

export async function render(main, [tabArg]) {
  const tab = TABS.find(t => t[0] === tabArg) ? tabArg : 'datasets';
  [formats, vocab] = await Promise.all([api.get('/api/formats'), api.get('/api/vocabulary')]);
  const st = await api.poll();
  main.innerHTML = `
  <div class="phead"><div><h1 style="font-size:1.7rem">Data Center</h1>
    <p>Add NASA, ESA, USGS or team datasets without rebuilding the website: upload → inspect → map fields → validate → process → activate. Every page reads from the same database and refreshes automatically.</p></div>
    <div class="card" style="padding:10px 12px" id="adminbox"></div></div>
  <div class="tabs" role="tablist">${TABS.map(([k, l]) => `<button role="tab" data-tab="${k}" class="${k === tab ? 'on' : ''}" aria-selected="${k === tab}">${l}</button>`).join('')}</div>
  <div id="tab"></div>`;
  $$('.tabs button', main).forEach(b => b.addEventListener('click', () => { location.hash = `#/data/${b.dataset.tab}`; }));
  adminBox(st);
  const fn = { datasets: datasetsTab, import: importTab, history: historyTab, formats: formatsTab, providers: providersTab }[tab];
  await fn($('#tab'));
  return {
    onRevision() { if (tab !== 'import' || W.step === 5) fn($('#tab')); },
  };
}

function adminBox(st) {
  const box = $('#adminbox');
  const draw = () => {
    if (api.admin.token) {
      box.innerHTML = `<div class="row small"><span class="cls verified">admin unlocked</span><button class="btn sm" id="lock">Lock</button></div>`;
      $('#lock').addEventListener('click', () => { api.admin.token = ''; draw(); });
    } else {
      box.innerHTML = st && !st.admin_configured
        ? '<span class="small muted">Admin operations are disabled on this server (no EARTHTWIN_ADMIN_TOKEN).</span>'
        : `<form class="row small" id="unlock"><label class="field" style="flex-direction:row;align-items:center;gap:6px"><span>Admin token</span>
             <input type="password" id="tok" autocomplete="current-password" style="width:170px"></label><button class="btn sm primary">Unlock</button></form>
           <p class="small dim" style="margin:4px 0 0">Needed to import or change data. Printed by <code>python run.py</code>.</p>`;
      $('#unlock')?.addEventListener('submit', async e => {
        e.preventDefault();
        api.admin.token = $('#tok').value.trim();
        try { await api.post('/api/admin/check'); toast('Data Center unlocked.'); draw(); }
        catch (err) { api.admin.token = ''; toast(err.message, true); }
      });
    }
  };
  draw();
}

// ------------------------------------------------------------------ datasets
async function datasetsTab(el) {
  const ds = await api.get('/api/datasets', { fresh: true });
  const ready = ds.filter(d => d.status !== 'planned');
  const planned = ds.filter(d => d.status === 'planned');
  const rowsHtml = list => list.map(d => `<tr class="click" data-id="${esc(d.id)}">
      <td><a href="#/dataset/${encodeURIComponent(d.id)}">${esc(d.name)}</a><br><span class="small dim">${esc(d.publisher || '')}</span></td>
      <td>${cls(d.data_class)}</td><td class="small">${esc(d.data_type.replace('_', ' '))}<br><span class="dim">${esc(d.file_format || '')}</span></td>
      <td class="small">${esc(d.body || '')}</td><td>${status(d.status)}</td>
      <td class="num">${d.n_observations}</td><td class="num">${d.n_records}</td><td class="num">${d.n_layers}</td>
      <td>${d.status === 'ready' ? `<label class="check"><input type="checkbox" data-act="${esc(d.id)}" ${d.active ? 'checked' : ''}> ${d.active ? 'active' : 'inactive'}</label>` : '<span class="dim small">—</span>'}</td></tr>`).join('');
  el.innerHTML = `
    <div class="card"><div class="row between"><h3 style="margin:0">Datasets in EarthTwin</h3><a class="btn sm primary" href="#/data/import">+ Import data</a></div>
    <p class="small muted">Deactivate a dataset to remove its records and measurements from every page and score without deleting it. Deactivating the demonstration dataset switches EarthTwin to verified-only results.</p>
    <div class="tablewrap"><table><thead><tr><th>Dataset</th><th>Class</th><th>Type</th><th>Body</th><th>Status</th><th class="num">Values</th><th class="num">Records</th><th class="num">Layers</th><th>Active</th></tr></thead>
    <tbody>${rowsHtml(ready) || '<tr><td colspan="9" class="dim">No datasets imported.</td></tr>'}</tbody></table></div></div>
    <div class="card" style="margin-top:14px"><h3>Catalogued sources — not yet integrated</h3>
    <p class="small muted">The pipeline is designed for these products. They are listed for transparency only: nothing from them is used until a file is imported and processed.</p>
    <div class="tablewrap"><table><thead><tr><th>Product</th><th>Body</th><th>Resolution</th><th>Route</th><th>Source</th></tr></thead><tbody>
    ${planned.map(d => `<tr><td><a href="#/dataset/${encodeURIComponent(d.id)}">${esc(d.name)}</a><br><span class="small dim">${esc(d.identifier || '')}</span></td><td>${esc(d.body)}</td><td class="small">${esc(d.spatial_resolution || '')}</td>
      <td class="small">${esc(d.description || '')}</td><td>${safeUrl(d.source_url) ? `<a href="${safeUrl(d.source_url)}" target="_blank" rel="noopener">source ↗</a>` : ''}</td></tr>`).join('')}</tbody></table></div></div>`;
  $$('[data-act]', el).forEach(cb => cb.addEventListener('click', async e => {
    e.stopPropagation();
    try { await api.post(`/api/datasets/${cb.dataset.act}/activate?active=${cb.checked}`); await api.invalidate(); toast(cb.checked ? 'Dataset activated — views refreshed.' : 'Dataset deactivated — views refreshed.'); }
    catch (err) { cb.checked = !cb.checked; toast(err.message, true); }
  }));
}

// ------------------------------------------------------------------ history
async function historyTab(el) {
  const imps = await api.get('/api/imports', { fresh: true });
  el.innerHTML = `<div class="card"><h3>Import history</h3><p class="small muted">Failed imports are kept with their error so nothing is presented as successful by mistake.</p>
    <div class="tablewrap"><table><thead><tr><th>File</th><th>Format</th><th>Kind</th><th>Status</th><th>Size</th><th>Updated</th><th>Result / error</th></tr></thead><tbody>
    ${imps.map(i => `<tr><td>${esc(i.original_filename)}</td><td>${esc(i.detected_format)}</td><td>${esc(i.import_kind || '')}</td><td>${status(i.status)}</td><td class="small">${bytes(i.size_bytes)}</td>
      <td class="small">${fmtDate(i.updated_at)}</td><td class="small">${i.dataset_id ? `<a href="#/dataset/${encodeURIComponent(i.dataset_id)}">dataset →</a>` : ''} ${i.job_error ? `<span style="color:var(--bad)">${esc(i.job_error)}</span>` : ''}
      ${['inspected', 'validated', 'invalid'].includes(i.status) ? `<button class="btn sm" data-resume="${esc(i.id)}">Resume</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="7" class="dim">No imports yet.</td></tr>'}
    </tbody></table></div></div>`;
  $$('[data-resume]', el).forEach(b => b.addEventListener('click', async () => {
    const s = await api.get(`/api/imports/${b.dataset.resume}`, { fresh: true });
    Object.assign(W, { session: s, kind: s.import_kind, mapping: s.confirmed_mapping || s.proposed_mapping, metadata: s.metadata, step: s.validation ? 4 : 3, job: null });
    location.hash = '#/data/import';
  }));
}

// ------------------------------------------------------------------ formats & templates
function formatsTab(el) {
  const f = formats;
  el.innerHTML = `
  <div class="grid g2">
    <div class="card"><h3>Supported formats</h3><table><tbody>${Object.entries(f.formats).map(([k, v]) => `<tr><td><b>${esc(k)}</b></td><td class="small">${esc(v.label)}<br><span class="dim">kinds: ${v.kinds.map(esc).join(', ')}</span></td></tr>`).join('')}</tbody></table>
      <p class="small muted">Limits: tables ${f.limits_mb.table} MB, rasters ${f.limits_mb.raster} MB. Rasters are processed on the server with windowed reads around each site/target.</p></div>
    <div class="card"><h3>Not supported directly</h3><ul class="small">${Object.entries(f.unsupported_guidance).map(([k, v]) => `<li><b>${esc(k)}</b> — ${esc(v)}</li>`).join('')}</ul></div>
    <div class="card"><h3>Import kinds</h3><ul class="small">${Object.entries(f.import_kinds).map(([k, v]) => `<li><b>${esc(k)}</b> — ${esc(v)}</li>`).join('')}</ul></div>
    <div class="card"><h3>Templates</h3><p class="small muted">Start from a template to get the expected structure.</p>
      <ul>${f.templates.map(t => `<li><a href="/templates/${encodeURIComponent(t)}" download>${esc(t)}</a></li>`).join('')}</ul>
      <p class="small">Full field documentation: <code>docs/DATA_DICTIONARY.md</code> in the repository.</p></div>
  </div>
  <div class="card" style="margin-top:14px"><h3>Variables &amp; accepted units</h3><div class="tablewrap"><table><thead><tr><th>Variable key</th><th>Name</th><th>Family</th><th>Type</th><th>Canonical unit</th><th>Accepted units / values</th></tr></thead><tbody>
    ${vocab.variables.map(v => `<tr><td><code>${esc(v.key)}</code></td><td>${esc(v.name)}</td><td>${esc(v.family)}</td><td>${esc(v.value_type)}</td><td>${esc(v.canonical_unit || '—')}</td>
      <td class="small">${(f.accepted_units[v.key] || v.allowed_values || []).map(esc).join(', ') || (v.value_type === 'boolean' ? 'yes/no, true/false, 1/0, present/absent' : '')}</td></tr>`).join('')}</tbody></table></div>
    <p class="small muted">Coordinates: Earth sites use WGS 84 (EPSG:4326). Moon/Mars targets require an explicit longitude convention (${Object.keys(f.longitude_conventions).map(esc).join(', ')}) and latitude type (${Object.keys(f.latitude_types).map(esc).join(', ')}); they are stored as planetocentric, east-positive −180…180.</p></div>`;
}

// ------------------------------------------------------------------ providers
async function providersTab(el) {
  const prov = await api.get('/api/providers');
  el.innerHTML = `
  <div class="grid g2">${prov.map(p => `<div class="card"><div class="row between"><h3 style="margin:0">${esc(p.name)}</h3>${status(p.status)}</div>
    <p class="small muted">${esc(p.description)}</p>${safeUrl(p.url) ? `<a class="small" href="${safeUrl(p.url)}" target="_blank" rel="noopener">${esc(p.url)} ↗</a>` : ''}</div>`).join('')}</div>
  <div class="card" style="margin-top:14px"><h3>Search NASA Earthdata (CMR)</h3>
    <p class="small muted">Find a collection and pre-fill dataset metadata for an import. Data files must still be downloaded (Earthdata Login) and uploaded.</p>
    <form class="row" id="cmrf"><input id="cmrq" type="search" placeholder="e.g. NASADEM, MOD11A2, IMERG" style="flex:1;min-width:200px"><button class="btn primary">Search</button></form>
    <div id="cmrout" style="margin-top:10px"></div></div>`;
  $('#cmrf').addEventListener('submit', async e => {
    e.preventDefault();
    const out = $('#cmrout');
    out.innerHTML = '<p class="muted small">Searching NASA CMR…</p>';
    try {
      const r = await api.get(`/api/providers/nasa_cmr/search?q=${encodeURIComponent($('#cmrq').value)}`, { fresh: true });
      out.innerHTML = r.results.length ? r.results.map((c, i) => `<div class="card flat" style="margin-bottom:8px"><b>${esc(c.title)}</b> <span class="tag">${esc(c.short_name)} v${esc(c.version)}</span>
        <p class="small muted" style="margin:4px 0">${esc(c.data_center)} · ${esc(c.time_start || '')} → ${esc(c.time_end || 'present')}</p><p class="small">${esc(c.summary.slice(0, 280))}…</p>
        <button class="btn sm" data-pre="${i}">Use as metadata for next import</button></div>`).join('') : '<p class="small dim">No collections found.</p>';
      $$('[data-pre]', out).forEach(b => b.addEventListener('click', () => {
        W.prefill = r.results[+b.dataset.pre].metadata_prefill;
        toast('Metadata saved — it will pre-fill the next import.');
        location.hash = '#/data/import';
      }));
    } catch (err) { out.innerHTML = `<div class="notice warn small">${esc(err.message)}</div>`; }
  });
}

// ------------------------------------------------------------------ import wizard
const STEPS = ['Upload', 'Inspect', 'Map & describe', 'Validate', 'Process'];

function importTab(el) {
  el.innerHTML = `<div class="steps">${STEPS.map((s, i) => `<span class="${i + 1 === W.step ? 'on' : i + 1 < W.step ? 'done' : ''}">${i + 1 < W.step ? '✓' : i + 1}. ${s}</span>`).join('')}</div><div id="wz"></div>`;
  const wz = $('#wz', el);
  if (!api.admin.token) {
    wz.innerHTML = '<div class="empty"><h3>Unlock the Data Center</h3><p>Enter the admin token (top right) to import data. Viewing datasets does not require it.</p></div>';
    return;
  }
  ({ 1: stepUpload, 2: stepInspect, 3: stepMap, 4: stepValidate, 5: stepProcess })[W.step](wz, () => importTab(el));
}

function reset() { Object.assign(W, { step: 1, session: null, kind: null, mapping: null, metadata: null, job: null }); }

function stepUpload(wz, redraw) {
  wz.innerHTML = `<div class="card">
    <div class="drop" id="drop" tabindex="0" role="button" aria-label="Choose a file to upload">
      <h3>Drop a file here or click to choose</h3>
      <p class="small">CSV · JSON · GeoJSON · EarthTwin bundle · GeoTIFF — up to ${formats.limits_mb.table} MB (tables) / ${formats.limits_mb.raster} MB (rasters)</p>
      <input type="file" id="file" accept=".csv,.txt,.json,.geojson,.tif,.tiff" hidden></div>
    <p class="small muted" style="margin-top:10px">The file is stored, sniffed for its real format and inspected. Nothing is added to EarthTwin until you review the mapping and process it. Need a starting point? <a href="#/data/formats">Download a template</a>.</p>
    ${W.prefill ? `<div class="notice small">Metadata from NASA CMR will be pre-filled: <b>${esc(W.prefill.name)}</b> <button class="btn sm" id="clrpre">Clear</button></div>` : ''}</div>`;
  const inp = $('#file'), drop = $('#drop');
  const go = async f => {
    if (!f) return;
    drop.innerHTML = `<p>Uploading and inspecting <b>${esc(f.name)}</b> (${bytes(f.size)})…</p>`;
    try {
      const s = await api.upload(f);
      Object.assign(W, { session: s, kind: s.import_kind, mapping: s.proposed_mapping, metadata: { ...s.metadata, ...(W.prefill || {}) }, step: 2 });
      W.prefill = null;
      if (s.duplicate_of) toast(`This exact file was already imported as “${s.duplicate_of}”.`, true);
      redraw();
    } catch (e) { toast(e.message, true); stepUpload(wz, redraw); }
  };
  drop.addEventListener('click', () => inp.click());
  drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') inp.click(); });
  inp.addEventListener('change', () => go(inp.files[0]));
  drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('over'));
  drop.addEventListener('drop', e => { e.preventDefault(); drop.classList.remove('over'); go(e.dataTransfer.files[0]); });
  $('#clrpre')?.addEventListener('click', () => { W.prefill = null; redraw(); });
}

function previewTable(rows, cols) {
  if (!rows || !rows.length) return '<p class="small dim">No rows to preview.</p>';
  cols = cols || Object.keys(rows[0]);
  return `<div class="tablewrap"><table class="preview-table"><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>
    ${rows.map(r => `<tr>${cols.map(c => `<td title="${esc(typeof r[c] === 'object' ? JSON.stringify(r[c]) : r[c])}">${esc(typeof r[c] === 'object' && r[c] !== null ? JSON.stringify(r[c]) : r[c])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function stepInspect(wz, redraw) {
  const s = W.session, st = s.structure;
  const kinds = s.detected_format === 'geotiff' || s.detected_format === 'bundle' ? st.suggested_kinds
    : [...new Set([...st.suggested_kinds, 'earth_sites', 'target_regions', 'observations', 'observations_long', ...(s.detected_format === 'geojson' ? ['map_layer'] : [])])];
  let body = '';
  if (st.raster) {
    const r = st.raster;
    body = `<table><tbody>
      <tr><td>Size</td><td>${r.width} × ${r.height} px, ${r.count} band(s), ${esc(r.dtypes.join(', '))}</td></tr>
      <tr><td>CRS</td><td>${r.crs ? `<code>${esc(r.crs_name || r.crs)}</code>` : '<span style="color:var(--amber)">none embedded — you will need to declare it</span>'}</td></tr>
      <tr><td>Detected body</td><td>${esc(r.detected_body || 'unknown')} ${r.semi_major_m ? `<span class="dim">(ellipsoid a = ${(r.semi_major_m / 1000).toFixed(1)} km)</span>` : ''}</td></tr>
      <tr><td>Bounds</td><td class="mono small">${r.bounds.map(v => v.toFixed(4)).join(', ')}</td></tr>
      <tr><td>Resolution</td><td>${r.resolution.map(v => +v.toPrecision(5)).join(' × ')} ${r.is_geographic ? 'deg' : esc(r.linear_unit || '')}/px</td></tr>
      <tr><td>NoData · scale · offset</td><td>${esc(r.nodata)} · ${esc(r.scales[0])} · ${esc(r.offsets[0])}</td></tr>
      <tr><td>Units tag</td><td>${esc((r.units || []).join(', ') || 'none')}</td></tr></tbody></table>`;
  } else if (s.detected_format === 'bundle') {
    body = `<p>EarthTwin bundle v${esc(st.bundle_version)}: ${Object.entries(st.counts).map(([k, v]) => `${v} ${esc(k.replace('_', ' '))}`).join(', ')}.</p>${previewTable(st.preview)}`;
  } else {
    body = `<p class="small muted">${st.n_rows} rows · ${st.columns.length} columns${st.info && st.info.geometry_types ? ' · geometry: ' + Object.entries(st.info.geometry_types).map(([k, v]) => `${esc(k)} ×${v}`).join(', ') : ''}${st.info && st.info.ragged_rows ? ` · <span style="color:var(--amber)">${st.info.ragged_rows} rows have a different number of cells than the header</span>` : ''}</p>
      <div class="tablewrap"><table class="small"><thead><tr><th>Column</th><th>Non-empty</th><th>Numeric</th><th>Examples</th></tr></thead><tbody>
      ${st.columns.map(c => { const p = st.column_profile[c]; return `<tr><td><code>${esc(c)}</code></td><td>${p.non_empty}</td><td>${Math.round(p.numeric_fraction * 100)}%</td><td class="dim">${p.examples.map(esc).join(' · ')}</td></tr>`; }).join('')}</tbody></table></div>
      <h4 style="margin-top:12px">Preview</h4>${previewTable(st.preview, st.columns)}`;
  }
  wz.innerHTML = `<div class="card"><div class="row between"><h3 style="margin:0">${esc(s.original_filename)}</h3><span class="small muted">detected <b>${esc(s.detected_format)}</b> · ${bytes(s.size_bytes)} · sha256 <code>${esc(s.sha256.slice(0, 12))}</code></span></div>
    ${s.duplicate_of ? `<div class="notice warn small">An identical file was already imported as “${esc(s.duplicate_of)}”. You can still import it as a new dataset or version.</div>` : ''}
    <hr class="sep">${body}<hr class="sep">
    <label class="field" style="max-width:420px"><span>What does this file contain?</span><select id="kind">${kinds.map(k => `<option value="${esc(k)}" ${k === W.kind ? 'selected' : ''}>${esc(formats.import_kinds[k] || k)}</option>`).join('')}</select></label>
    <div class="row" style="margin-top:14px"><button class="btn" id="cancel">Cancel</button><button class="btn primary" id="next">Next: map fields →</button></div></div>`;
  $('#cancel').addEventListener('click', () => { reset(); redraw(); });
  $('#next').addEventListener('click', async () => {
    const k = $('#kind').value;
    if (k !== W.kind || !W.mapping) {
      try { W.mapping = await api.post(`/api/imports/${s.id}/propose?kind=${encodeURIComponent(k)}`); } catch (e) { return toast(e.message, true); }
      W.kind = k;
    }
    W.step = 3; redraw();
  });
}

const opt = (v, cur, label) => `<option value="${esc(v)}" ${v === cur ? 'selected' : ''}>${esc(label ?? v)}</option>`;

function metadataForm(md, kind) {
  const ds = (window.__etDatasets || []);
  const needBody = ['raster', 'map_layer', 'target_regions'].includes(kind);
  return `<h3>Dataset metadata &amp; provenance</h3>
  <div class="grid g3">
    <label class="field"><span class="req">Dataset name</span><input data-md="name" value="${esc(md.name)}"></label>
    <label class="field"><span class="req">Data class</span><select data-md="data_class">${opt('', md.data_class || '', 'Choose…')}${opt('verified', md.data_class, 'verified — values from an identified source')}${opt('demo', md.data_class, 'demo — illustrative test values')}${kind !== 'raster' ? opt('reference', md.data_class, 'reference — records/context only, no measurements') : ''}</select></label>
    <label class="field"><span class="${needBody ? 'req' : ''}">Body</span><select data-md="body">${opt('', md.body || '', kind === 'target_regions' ? 'From a body column' : 'Choose…')}${opt('earth', md.body, 'Earth')}${opt('moon', md.body, 'Moon')}${opt('mars', md.body, 'Mars')}${opt('mixed', md.body, 'Mixed')}</select></label>
    <label class="field"><span>Publisher / organisation <span class="dim">(required for verified)</span></span><input data-md="publisher" value="${esc(md.publisher)}"></label>
    <label class="field"><span>Source URL</span><input data-md="source_url" type="url" value="${esc(md.source_url)}" placeholder="https://"></label>
    <label class="field"><span>Identifier / DOI / product ID</span><input data-md="identifier" value="${esc(md.identifier)}"></label>
    <label class="field"><span>Licence / usage terms</span><input data-md="license" value="${esc(md.license)}"></label>
    <label class="field"><span>Version label</span><input data-md="version" value="${esc(md.version)}" placeholder="auto (v1, v2…)"></label>
    <label class="field"><span>Spatial resolution</span><input data-md="spatial_resolution" value="${esc(md.spatial_resolution)}"></label>
    <label class="field"><span>Temporal coverage</span><input data-md="temporal_coverage" value="${esc(md.temporal_coverage)}" placeholder="e.g. 2000-2020 climatology"></label>
    <label class="field"><span>CRS</span><input data-md="crs" value="${esc(md.crs || '')}" placeholder="${kind === 'earth_sites' ? 'EPSG:4326' : ''}"></label>
    <label class="field"><span>Method / instrument</span><input data-md="method" value="${esc(md.method)}"></label>
  </div>
  <div class="grid g2" style="margin-top:10px">
    <label class="field"><span>Description</span><textarea data-md="description">${esc(md.description)}</textarea></label>
    <label class="field"><span>Provenance / processing history before upload</span><textarea data-md="provenance">${esc(md.provenance)}</textarea></label>
    <label class="field"><span>Citation text</span><textarea data-md="citation_text">${esc(md.citation_text)}</textarea></label>
    <div class="stack"><label class="field"><span>Citation DOI</span><input data-md="citation_doi" value="${esc(md.citation_doi)}"></label>
      <label class="field"><span>Import as a new version of</span><select data-md="dataset_id">${opt('', md.dataset_id || '', '— a new dataset —')}${ds.filter(d => d.status === 'ready').map(d => opt(d.id, md.dataset_id, d.name)).join('')}</select></label>
      <label class="check"><input type="checkbox" data-md="activate" ${md.activate !== false ? 'checked' : ''}> Activate after successful processing</label></div>
  </div>`;
}

function readMetadata(wz) {
  const md = { ...W.metadata };
  $$('[data-md]', wz).forEach(i => { md[i.dataset.md] = i.type === 'checkbox' ? i.checked : (i.value === '' && ['dataset_id', 'body', 'data_class'].includes(i.dataset.md) ? null : i.value); });
  return md;
}

function tabularMapping(m, kind, cols) {
  const std = formats.standard_fields[kind] || {};
  const req = formats.required_fields[kind] || [];
  const vars = vocab.variables;
  const used = new Set([...Object.values(m.fields || {}), ...(m.variables || []).map(v => v.column)]);
  const varRow = (column, v) => {
    const vk = v ? v.variable : '';
    const vv = vars.find(x => x.key === vk);
    return `<tr><td><code>${esc(column)}</code></td>
      <td><select data-vcol="${esc(column)}">${opt('', vk, '— not imported —')}${vars.filter(x => !(kind === 'target_regions' && x.family === 'operational')).map(x => opt(x.key, vk, `${x.name} (${x.key})`)).join('')}</select></td>
      <td>${vv && vv.value_type === 'numeric' ? `<input data-vunit="${esc(column)}" value="${esc(v && v.unit ? v.unit : '')}" list="u-${esc(vk)}" placeholder="unit required">
        <datalist id="u-${esc(vk)}">${(formats.accepted_units[vk] || []).map(u => `<option value="${esc(u)}">`).join('')}</datalist>${v && v.unit_source === 'header' ? '<br><span class="conf low">from header — confirm</span>' : ''}` : `<span class="dim small">${vv ? esc(vv.value_type) : ''}</span>`}</td>
      <td>${v ? `<span class="conf ${esc(v.confidence)}">${esc(v.confidence)}</span>` : ''}</td></tr>`;
  };
  const fieldRows = Object.keys(std).filter(f => kind !== 'observations' || f === 'subject').map(f => `<tr><td>${req.includes(f) ? `<span class="req">${esc(f)}</span>` : esc(f)}</td>
      <td><select data-field="${esc(f)}">${opt('', m.fields[f] || '', '— none —')}${cols.map(c => opt(c, m.fields[f])).join('')}</select></td>
      <td>${m.field_confidence && m.field_confidence[f] ? `<span class="conf ${esc(m.field_confidence[f])}">${esc(m.field_confidence[f])}</span>` : ''}</td></tr>`).join('');
  const o = m.options || {};
  let options = `<label class="field"><span>List separator (categories, lithology)</span><select data-opt="list_separator">${opt('', o.list_separator || '', 'auto ; | ,')}${opt(';', o.list_separator)}${opt('|', o.list_separator)}${opt(',', o.list_separator)}</select></label>`;
  if (kind === 'target_regions') options += `
    <label class="field"><span class="req">Longitude convention</span><select data-opt="lon_convention">${opt('', o.lon_convention || '', 'Choose…')}${Object.entries(formats.longitude_conventions).map(([k, v]) => opt(k, o.lon_convention, v)).join('')}</select></label>
    <label class="field"><span class="req">Latitude type</span><select data-opt="lat_type">${opt('', o.lat_type || '', 'Choose…')}${Object.entries(formats.latitude_types).map(([k, v]) => opt(k, o.lat_type, v)).join('')}</select></label>`;
  if (kind === 'observations' || kind === 'observations_long') options += `
    <label class="field"><span class="req">Rows describe</span><select data-opt="subject_type">${opt('', o.subject_type || '', 'Choose…')}${opt('earth_site', o.subject_type, 'Earth sites')}${opt('target_region', o.subject_type, 'Moon/Mars target regions')}</select></label>
    <label class="field"><span class="req">Match rows to records by</span><select data-opt="match_by">${opt('', o.match_by || '', 'Choose…')}${opt('id', o.match_by, 'id (e.g. atacama-yungay)')}${opt('name', o.match_by, 'exact name')}</select></label>`;
  const showVars = kind !== 'observations_long';
  return `<h3>Field mapping</h3><p class="small muted">Suggestions are marked with a confidence. Review every row — units and coordinate conventions are never applied without your confirmation.</p>
    <div class="grid g2"><div><h4>Standard fields</h4><table class="maptable"><thead><tr><th>EarthTwin field</th><th>Source column</th><th></th></tr></thead><tbody>${fieldRows}</tbody></table></div>
    <div><h4>Options</h4><div class="stack">${options}</div></div></div>
    ${showVars ? `<h4 style="margin-top:14px">Measurement columns</h4><div class="tablewrap"><table class="maptable"><thead><tr><th>Column</th><th>EarthTwin variable</th><th>Unit</th><th>Confidence</th></tr></thead><tbody>
      ${cols.filter(c => !Object.values(m.fields || {}).includes(c) && !c.startsWith('_geometry')).map(c => varRow(c, (m.variables || []).find(v => v.column === c))).join('')}</tbody></table></div>
      <p class="small dim">Columns left as “not imported” are ${kind === 'observations' ? 'kept in the stored original file' : "preserved in each record's extra fields"} and listed in the validation report.</p>` : ''}`;
}

function readTabular(wz, kind) {
  const m = { kind, fields: {}, variables: [], options: {} };
  $$('[data-field]', wz).forEach(s => { if (s.value) m.fields[s.dataset.field] = s.value; });
  $$('[data-opt]', wz).forEach(s => { m.options[s.dataset.opt] = s.value || null; });
  $$('[data-vcol]', wz).forEach(s => {
    if (!s.value) return;
    const u = $(`[data-vunit="${CSS.escape(s.dataset.vcol)}"]`, wz);
    const prev = (W.mapping.variables || []).find(v => v.column === s.dataset.vcol) || {};
    m.variables.push({ column: s.dataset.vcol, variable: s.value, unit: u ? u.value.trim() || null : null, confidence: prev.variable === s.value ? prev.confidence : 'user', unit_source: 'user' });
  });
  return m;
}

function rasterMapping(m) {
  const r = m.raster || {};
  const st = W.session.structure.raster;
  const numeric = vocab.variables.filter(v => v.value_type === 'numeric' && v.family !== 'operational');
  return `<h3>Raster processing</h3>
  <div class="grid g3">
    <label class="field"><span class="req">Raster contains</span><select data-r="raster_kind">${opt('', r.raster_kind || '', 'Choose…')}${Object.entries(formats.raster_kinds).map(([k, v]) => opt(k, r.raster_kind, v.label)).join('')}</select></label>
    <label class="field"><span>Variable (scalar rasters)</span><select data-r="variable">${opt('', r.variable || '', '—')}${numeric.map(v => opt(v.key, r.variable, v.name)).join('')}</select></label>
    <label class="field"><span class="req">Pixel value unit</span><input data-r="unit" value="${esc(r.unit || '')}" placeholder="e.g. m, km, K, °C, mm/yr, fraction">${r.unit_source === 'file' ? '<span class="conf low">from file metadata — confirm</span>' : ''}</label>
    ${!st.crs ? `<label class="field"><span class="req">Declared CRS (file has none)</span><input data-r="declared_crs" value="${esc(r.declared_crs || '')}" placeholder="EPSG:4326 / IAU_2015:30100 / IAU_2015:49900"></label>` : ''}
  </div>
  <p class="small muted">Elevation rasters produce mean elevation, local relief (P95−P5), mean slope and slope variability for every site or target region of the dataset's body inside the raster coverage, using each record's analysis window. Values become <span class="cls derived">derived</span> when the raster is verified, otherwise <span class="cls demo">demo</span>.</p>`;
}
function readRaster(wz) {
  const r = {};
  $$('[data-r]', wz).forEach(i => { r[i.dataset.r] = i.value.trim() || null; });
  return { kind: 'raster', raster: r };
}
function layerMapping(m) {
  const l = m.layer || {};
  const cols = W.session.structure.columns.filter(c => !c.startsWith('_geometry'));
  return `<h3>Map layer</h3><div class="grid g3">
    <label class="field"><span>Layer name</span><input data-l="name" value="${esc(l.name || '')}" placeholder="defaults to dataset name"></label>
    <label class="field"><span>Label property</span><select data-l="label_property">${opt('', l.label_property || '', '—')}${cols.map(c => opt(c, l.label_property)).join('')}</select></label>
    <label class="field"><span>Colour</span><input data-l="color" type="color" value="${esc(l.color || '#38bdf8')}"></label></div>
    <p class="small muted">GeoJSON coordinates must be longitude/latitude in the body's geographic CRS (RFC 7946). Moon/Mars layers appear only on the planetary maps.</p>`;
}
function readLayer(wz) {
  const l = {};
  $$('[data-l]', wz).forEach(i => { l[i.dataset.l] = i.value || null; });
  return { kind: 'map_layer', layer: l };
}

async function stepMap(wz, redraw) {
  window.__etDatasets = await api.get('/api/datasets');
  const s = W.session, k = W.kind;
  let mapHtml = '';
  if (k === 'raster') mapHtml = rasterMapping(W.mapping);
  else if (k === 'map_layer') mapHtml = layerMapping(W.mapping);
  else if (k === 'bundle') mapHtml = '<h3>Bundle</h3><p class="small muted">Bundles are self-describing: fields use EarthTwin names. Metadata below is pre-filled from the bundle and can be edited.</p>';
  else mapHtml = tabularMapping(W.mapping, k, s.structure.columns);
  wz.innerHTML = `<div class="card">${mapHtml}</div><div class="card" style="margin-top:14px">${metadataForm(W.metadata, k)}</div>
    <div class="row" style="margin-top:14px"><button class="btn" id="back">← Back</button><button class="btn primary" id="val">Validate (no changes made yet) →</button></div>`;
  const collect = () => {
    W.metadata = readMetadata(wz);
    W.mapping = k === 'raster' ? { ...W.mapping, ...readRaster(wz) } : k === 'map_layer' ? { ...W.mapping, ...readLayer(wz) } : k === 'bundle' ? { kind: 'bundle' } : { ...W.mapping, ...readTabular(wz, k) };
  };
  $$('[data-vcol]', wz).forEach(sel => sel.addEventListener('change', () => { collect(); stepMap(wz, redraw); }));
  $('#back').addEventListener('click', () => { collect(); W.step = 2; redraw(); });
  $('#val').addEventListener('click', async () => {
    collect();
    $('#val').disabled = true;
    try {
      W.session = await api.put(`/api/imports/${s.id}/mapping`, { kind: k, mapping: W.mapping, metadata: W.metadata });
      W.step = 4; redraw();
    } catch (e) { toast(e.message, true); $('#val').disabled = false; }
  });
}

function stepValidate(wz, redraw) {
  const v = W.session.validation || {};
  const iss = v.issues || [];
  const errs = iss.filter(i => i.level === 'error'), warns = iss.filter(i => i.level === 'warning');
  const prev = v.preview_records || {};
  wz.innerHTML = `<div class="card">
    <div class="row between"><h3 style="margin:0">Validation report</h3>${status(W.session.status)}</div>
    <div class="grid g4" style="margin:12px 0">
      <div class="kpi"><span class="v">${v.n_records ?? 0}</span><span class="l">records in file</span></div>
      <div class="kpi"><span class="v">${v.n_valid ?? 0}</span><span class="l">valid records</span></div>
      <div class="kpi"><span class="v">${v.n_rejected ?? 0}</span><span class="l">rejected rows</span></div>
      <div class="kpi"><span class="v">${warns.length}</span><span class="l">warnings</span></div></div>
    ${v.note ? `<p class="small">${esc(v.note)}</p>` : ''}
    ${v.observations_by_variable && Object.keys(v.observations_by_variable).length ? `<p class="small">Measurements to store: ${Object.entries(v.observations_by_variable).map(([k, n]) => `<code>${esc(k)}</code> ×${n}`).join(', ')}</p>` : ''}
    ${v.unused_columns && v.unused_columns.length ? `<p class="small muted">Unmapped columns: ${v.unused_columns.map(c => `<code>${esc(c)}</code>`).join(' ')} — ${esc(v.unused_columns_note || '')}</p>` : ''}
    ${iss.length ? `<h4>Issues${v.n_issues_total > iss.length ? ` (first ${iss.length} of ${v.n_issues_total})` : ''}</h4><ul class="issues">${iss.map(i => `<li class="${esc(i.level)}"><b>${esc(i.level)}</b>${i.section ? ` [${esc(i.section)}]` : ''}${i.row ? ` row ${i.row}` : ''}${i.column ? ` · ${esc(i.column)}` : ''}: ${esc(i.message)}</li>`).join('')}</ul>` : '<p class="small" style="color:var(--ok)">No issues found.</p>'}
    ${errs.length && W.session.status === 'invalid' ? '<div class="notice err small">Fix the blocking errors (go back to the mapping step, or correct the file and upload it again). Row-level errors only reject those rows.</div>' : ''}
    ${Object.entries(prev).filter(([, l]) => l.length).map(([k, l]) => `<h4 style="margin-top:12px">Normalised ${esc(k.replace('_', ' '))} (preview)</h4>${previewTable(l.map(x => ({ ...x, value: Array.isArray(x.value) ? x.value.join(';') : x.value, extra: x.extra ? JSON.stringify(x.extra) : undefined })))}`).join('')}
    <div class="row" style="margin-top:14px"><button class="btn" id="back">← Edit mapping</button>
      <button class="btn primary" id="go" ${W.session.status !== 'validated' ? 'disabled' : ''}>Process &amp; ${W.metadata.activate === false ? 'store' : 'activate'} →</button></div></div>`;
  $('#back').addEventListener('click', () => { W.step = 3; redraw(); });
  $('#go').addEventListener('click', async () => {
    $('#go').disabled = true;
    try { W.job = await api.post(`/api/imports/${W.session.id}/process`); W.step = 5; redraw(); }
    catch (e) { toast(e.message, true); $('#go').disabled = false; }
  });
}

let jobTimer = null;
function stepProcess(wz, redraw) {
  const draw = target => {
    const j = W.job;
    const done = j.status === 'succeeded', failed = j.status === 'failed';
    target.innerHTML = `<div class="card"><div class="row between"><h3 style="margin:0">Processing</h3>${status(j.status)}</div>
      <div class="log" style="margin-top:10px">${(j.log || []).filter(l => l.step !== 'trace').map(l => `${esc(l.at.slice(11, 19))}  ${esc(l.step.padEnd(18))} ${esc(l.detail)}`).join('\n') || 'Waiting…'}</div>
      ${done ? `<div class="notice" style="margin-top:12px"><b>Import complete.</b> ${esc(summaryText(j.result))} Every page now reflects the new data.
        <div class="row" style="margin-top:8px"><a class="btn sm primary" href="#/dataset/${encodeURIComponent(j.result.dataset_id)}">Open dataset</a><a class="btn sm" href="#/explore">See updated rankings</a><a class="btn sm" href="#/catalogue">Catalogue</a><button class="btn sm" id="again">Import another file</button></div></div>` : ''}
      ${failed ? `<div class="notice err" style="margin-top:12px"><b>Processing failed — nothing was changed.</b> ${esc(j.error)}<div class="row" style="margin-top:8px"><button class="btn sm" id="remap">Back to mapping</button><button class="btn sm" id="again">Start over</button></div></div>` : ''}</div>`;
    $('#again', target)?.addEventListener('click', () => { reset(); redraw(); });
    $('#remap', target)?.addEventListener('click', async () => { W.session = await api.get(`/api/imports/${W.session.id}`, { fresh: true }); W.step = 3; redraw(); });
  };
  draw(wz);
  // One poller for the whole wizard: it always draws into the wizard container currently on the page,
  // so a background re-render (data revision) can never strand the view on a stale status.
  clearTimeout(jobTimer);
  const tick = async () => {
    if (W.step !== 5 || !W.job) return;
    const wasRunning = !['succeeded', 'failed'].includes(W.job.status);
    if (wasRunning) { try { W.job = await api.get(`/api/jobs/${W.job.id}`, { fresh: true }); } catch { /* retry */ } }
    const cur = document.getElementById('wz');
    if (cur && W.step === 5) draw(cur);
    if (['succeeded', 'failed'].includes(W.job.status)) {
      if (wasRunning) { api.invalidate(); if (W.job.status === 'succeeded') toast('Dataset processed — EarthTwin updated.'); }
    } else jobTimer = setTimeout(tick, 700);
  };
  jobTimer = setTimeout(tick, 300);
}

function summaryText(r) {
  if (!r) return '';
  if (r.kind === 'raster') return `${r.observations} derived values for ${r.subjects_covered} of ${r.subjects_checked} subjects.`;
  if (r.kind === 'map_layer') return `${r.features} features added as a map layer.`;
  return `${r.sites_created || 0} sites created, ${r.sites_updated || 0} updated; ${r.targets_created || 0} targets created, ${r.targets_updated || 0} updated; ${r.observations || 0} measurements stored (version ${r.version}).`;
}
