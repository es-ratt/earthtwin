import * as api from '../api.js';
import { $, $$, esc, bytes, citeList, cls, fmtDate, safeUrl, status, toast } from '../ui.js';

const EDITABLE = ['name', 'publisher', 'source_url', 'identifier', 'license', 'spatial_resolution', 'temporal_coverage', 'crs', 'description', 'provenance'];

export async function render(main, [id]) {
  const d = await api.get(`/api/datasets/${encodeURIComponent(id)}`, { fresh: true });
  const canEdit = !!api.admin.token;
  const cur = d.versions.find(v => v.id === d.current_version_id);
  const q = d.quality[0];
  main.innerHTML = `
  <div class="crumbs"><a href="#/data">Data Center</a> / dataset</div>
  <div class="phead"><div><h1 style="font-size:1.7rem">${esc(d.name)}</h1>
    <p>${cls(d.data_class)} ${status(d.status)} ${d.active ? '<span class="cls verified">active</span>' : '<span class="cls missing">inactive</span>'} · ${esc(d.data_type.replace('_', ' '))} · ${esc(d.body || '')}</p></div>
    ${canEdit && d.status === 'ready' ? `<div class="row"><button class="btn" id="tog">${d.active ? 'Deactivate' : 'Activate'}</button><button class="btn danger" id="del">Delete…</button></div>` : ''}</div>
  ${d.data_class === 'demo' ? '<div class="notice warn small"><b>DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT.</b> Values in this dataset are illustrative.</div>' : ''}
  ${d.status === 'planned' ? '<div class="notice small">Catalogue entry only. This product has <b>not</b> been downloaded or processed and contributes nothing to any score. Download a file from the source and import it in the Data Center.</div>' : ''}
  <div id="delbox"></div>
  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h3>Metadata &amp; provenance</h3>
      <form id="mdf"><table><tbody>${EDITABLE.map(k => `<tr><td class="dim" style="width:34%">${esc(k.replace('_', ' '))}</td><td>${canEdit && d.status !== 'planned'
        ? (k === 'description' || k === 'provenance' ? `<textarea name="${k}">${esc(d[k] || '')}</textarea>` : `<input name="${k}" value="${esc(d[k] || '')}" style="width:100%">`)
        : (k === 'source_url' && safeUrl(d[k]) ? `<a href="${safeUrl(d[k])}" target="_blank" rel="noopener">${esc(d[k])} ↗</a>` : esc(d[k] || '—'))}</td></tr>`).join('')}
        <tr><td class="dim">units</td><td class="small">${Object.entries(d.units || {}).map(([k, v]) => `${esc(k)}: ${esc(v)}`).join('; ') || '—'}</td></tr>
        <tr><td class="dim">created · updated</td><td class="small">${fmtDate(d.created_at)} · ${fmtDate(d.updated_at)}</td></tr></tbody></table>
      ${canEdit && d.status !== 'planned' ? '<button class="btn sm primary" style="margin-top:8px">Save metadata</button>' : ''}</form></div>
    <div class="card"><h3>Contents</h3>
      <div class="grid g3"><div class="kpi"><span class="v">${d.n_observations}</span><span class="l">measurements (current version)</span></div>
        <div class="kpi"><span class="v">${d.n_records}</span><span class="l">site / target records</span></div>
        <div class="kpi"><span class="v">${d.n_layers}</span><span class="l">map layers</span></div></div>
      ${d.variables.length ? `<table style="margin-top:10px"><thead><tr><th>Variable</th><th>Subjects</th><th class="num">Values</th></tr></thead><tbody>${d.variables.map(v => `<tr><td><code>${esc(v.variable_key)}</code></td><td>${esc(v.subject_type.replace('_', ' '))}</td><td class="num">${v.n}</td></tr>`).join('')}</tbody></table>` : ''}
      ${d.layers.length ? `<h4 style="margin-top:12px">Layers</h4><ul class="small">${d.layers.map(l => `<li>${esc(l.name)} · ${esc(l.body)} · ${esc(l.kind)}${l.feature_count ? ` · ${l.feature_count} features` : ''}</li>`).join('')}</ul>` : ''}
      ${q ? `<h4 style="margin-top:12px">Data quality (latest)</h4><p class="small">${esc(q.summary)} · completeness ${Math.round((q.completeness || 0) * 100)}%</p>
        ${q.issues.length ? `<details><summary class="small" style="cursor:pointer">${q.issues.length} recorded issues</summary><ul class="issues">${q.issues.slice(0, 200).map(i => `<li class="${esc(i.level)}">${i.row ? `row ${i.row}: ` : ''}${i.subject ? esc(i.subject) + ': ' : ''}${esc(i.message)}</li>`).join('')}</ul></details>` : ''}` : ''}</div>
  </div>
  <div class="card" style="margin-top:14px"><h3>Versions</h3>
    ${d.versions.length ? `<div class="tablewrap"><table><thead><tr><th>Version</th><th>File</th><th>Size</th><th>sha256</th><th>Imported</th><th>Processing history</th><th></th></tr></thead><tbody>
    ${d.versions.map(v => `<tr${v.id === d.current_version_id ? ' class="sel"' : ''}><td><b>${esc(v.version)}</b>${v.id === d.current_version_id ? ' <span class="cls verified">current</span>' : ''}</td><td class="small">${esc(v.original_filename || '')}</td><td class="small">${v.size_bytes ? bytes(v.size_bytes) : ''}</td>
      <td class="mono small">${esc((v.sha256 || '').slice(0, 12))}</td><td class="small">${fmtDate(v.created_at)}</td>
      <td class="small">${v.processing_history.map(h => `${esc(h.step)}: ${esc(h.detail)}`).join('<br>')}</td>
      <td>${canEdit && v.id !== d.current_version_id ? `<button class="btn sm" data-ver="${esc(v.id)}">Make current</button>` : ''}</td></tr>`).join('')}</tbody></table></div>` : '<p class="small dim">No files imported for this dataset.</p>'}
    ${cur ? `<details style="margin-top:8px"><summary class="small" style="cursor:pointer">Field mapping used for ${esc(cur.version)}</summary><pre class="log">${esc(JSON.stringify(cur.field_mapping, null, 2))}</pre></details>` : ''}</div>
  <div class="card" style="margin-top:14px"><h3>Citations</h3>${citeList(d.citations)}</div>
  ${d.jobs.length ? `<div class="card" style="margin-top:14px"><h3>Processing jobs</h3><table><tbody>${d.jobs.map(j => `<tr><td class="mono small">${esc(j.id.slice(0, 10))}</td><td>${esc(j.kind)}</td><td>${status(j.status)}</td><td class="small">${fmtDate(j.finished_at)}</td><td class="small">${esc(j.error || '')}</td></tr>`).join('')}</tbody></table></div>` : ''}`;

  $('#mdf')?.addEventListener('submit', async e => {
    e.preventDefault();
    const body = {};
    $$('#mdf [name]').forEach(i => { body[i.name] = i.value; });
    try { await api.patch(`/api/datasets/${d.id}`, body); await api.invalidate(); toast('Metadata saved.'); } catch (err) { toast(err.message, true); }
  });
  $('#tog')?.addEventListener('click', async () => {
    try { await api.post(`/api/datasets/${d.id}/activate?active=${!d.active}`); await api.invalidate(); toast(d.active ? 'Dataset deactivated.' : 'Dataset activated.'); }
    catch (err) { toast(err.message, true); }
  });
  $('#del')?.addEventListener('click', () => {
    $('#delbox').innerHTML = `<div class="notice err" style="margin-top:12px">Delete <b>${esc(d.name)}</b> and all its versions, measurements, layers and stored files? This cannot be undone. Deactivating is reversible.
      <div class="row" style="margin-top:8px"><button class="btn sm danger" id="delyes">Delete permanently</button><button class="btn sm" id="delno">Cancel</button></div></div>`;
    $('#delno').addEventListener('click', () => { $('#delbox').innerHTML = ''; });
    $('#delyes').addEventListener('click', async () => {
      try { await api.del(`/api/datasets/${d.id}`); await api.invalidate(); toast('Dataset deleted.'); location.hash = '#/data'; }
      catch (err) { toast(err.message, true); }
    });
  });
  $$('[data-ver]', main).forEach(b => b.addEventListener('click', async () => {
    try { await api.post(`/api/datasets/${d.id}/versions/${b.dataset.ver}/current`); await api.invalidate(); toast('Current version changed.'); }
    catch (err) { toast(err.message, true); }
  }));
}
