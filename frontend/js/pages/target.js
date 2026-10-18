import * as api from '../api.js';
import { planetMap } from '../maps.js';
import { set } from '../store.js';
import { $, esc } from '../ui.js';
import { targetDetail } from './targets.js';

export async function render(main, [id]) {
  const t = await api.get(`/api/targets/${encodeURIComponent(id)}`);
  main.innerHTML = `<div class="crumbs"><a href="#/targets/${esc(t.world_id)}">Targets</a> / ${esc(t.world?.name || t.world_id)}</div>
    <div class="card" id="det">${targetDetail(t, false)}</div>
    <div class="card mapcard" style="padding:0;overflow:hidden;margin-top:14px"><div id="tmap" style="height:420px"></div></div>
    <p class="small dim">${esc(t.world?.description || '')}</p>`;
  $('#usebtn').addEventListener('click', () => { set({ targetId: t.id, selected: null }); location.hash = '#/explore'; });
  const pm = await planetMap($('#tmap'), t.world_id);
  pm.setTargets([t], t.id);
  return { destroy() { pm.map.remove(); } };
}
