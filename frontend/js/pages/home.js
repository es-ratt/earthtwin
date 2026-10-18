import * as api from '../api.js';
import { earthMap } from '../maps.js';
import { $, esc, cls, CAT_LABEL, WORLD } from '../ui.js';

export async function render(main) {
  const [st, sites, targets, datasets] = await Promise.all([api.poll(), api.get('/api/sites'), api.get('/api/targets'), api.get('/api/datasets')]);
  const byClass = c => datasets.filter(d => d.data_class === c && d.active).length;
  const planned = datasets.filter(d => d.status === 'planned').length;
  const nObs = datasets.reduce((a, d) => a + (d.active ? d.n_observations : 0), 0);
  main.innerHTML = `
  <section class="hero">
    <div>
      <div class="eyebrow">NASA Space Apps Challenge 2026 · Team PLANEX</div>
      <h1>Finding Earth's best analogs for the Moon and Mars.</h1>
      <p class="lead">EarthTwin compares measured characteristics of Earth locations with lunar and Martian target regions, shows the evidence behind every match — and where the evidence runs out.</p>
      <div class="row" style="margin:18px 0 10px">
        <a class="btn primary" href="#/explore">Explore Earth analogs →</a>
        <a class="btn" href="#/targets">Browse Moon &amp; Mars targets</a>
        <a class="btn" href="#/methodology">How scoring works</a>
      </div>
      <div class="grid" style="margin-top:22px;grid-template-columns:repeat(auto-fit,minmax(130px,1fr))">
        <div class="kpi"><span class="v">${sites.length}</span><span class="l">Earth candidate sites</span></div>
        <div class="kpi"><span class="v">${targets.filter(t => t.world_id === 'moon').length} / ${targets.filter(t => t.world_id === 'mars').length}</span><span class="l">Moon / Mars target regions</span></div>
        <div class="kpi"><span class="v">${nObs}</span><span class="l">active measurements</span></div>
        <div class="kpi"><span class="v">${planned}</span><span class="l">NASA datasets catalogued, not yet integrated</span></div>
      </div>
    </div>
    <div>
      <div class="preview" id="pmap" aria-label="Map preview of candidate Earth analog sites"></div>
      <p class="small dim" style="margin-top:6px">Preview: candidate Earth sites in the active catalogue. Open the Explorer to score them against a target.</p>
    </div>
  </section>

  ${st && st.mode === 'demo' ? `<div class="notice warn"><b>You are viewing demonstration data.</b> All similarity values currently shown in EarthTwin come from illustrative placeholder measurements (labelled <span class="cls demo">demo</span>). The pipeline is ready for verified NASA, ESA and USGS datasets: import them in the <a href="#/data">Data Center</a> and every page updates automatically.</div>` : ''}

  <section class="section">
    <h2>The challenge</h2>
    <div class="grid g2">
      <div class="card"><h4>Problem statement</h4>
        <p>“Selecting future landing sites and lunar base locations depends on many factors, including topography, geology, environment, and available resources … Places on Earth that have analogous characteristics to the Moon or Mars – the Atacama Desert, Haughton Crater, Death Valley – allow mission teams to test equipment and methods before they fly; however, such terrestrial analog sites are not entirely well characterized.”</p>
        <p class="small dim">— NASA Space Apps Challenge 2026: Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars</p></div>
      <div class="card"><h4>What is a terrestrial analog?</h4>
        <p>An analog is a place on Earth that shares <em>some</em> relevant conditions with a target on another world — slopes a rover must climb, basaltic rock a drill must cut, ground ice a base might mine, or extreme dryness and cold. No Earth site reproduces lunar or Martian gravity, vacuum or radiation, so an analog is always partial.</p>
        <p>EarthTwin makes that partiality explicit: it scores similarity criterion by criterion, shows important differences, and refuses to score when data are insufficient.</p></div>
    </div>
  </section>

  <section class="section">
    <h2>How EarthTwin compares worlds</h2>
    <p class="sub">The same pipeline handles the demonstration data and the verified datasets PLANEX imports later.</p>
    <div class="flow card">
      <div><b>Import</b><span>CSV, JSON, GeoJSON, GeoTIFF from NASA, ESA, USGS…</span></div>
      <div><b>Validate &amp; map</b><span>Units, coordinates and planetary CRS checked — never guessed</span></div>
      <div><b>Extract features</b><span>Relief, slope, roughness from DEMs; window statistics from rasters</span></div>
      <div><b>Compare</b><span>Per-criterion similarity, weighted index, coverage reported separately</span></div>
      <div><b>Explain &amp; export</b><span>Evidence, mismatches, citations, CSV and PDF reports</span></div>
    </div>
  </section>

  <section class="section">
    <h2>Scientific capabilities</h2>
    <div class="grid g3">
      <div class="card"><h3>Transparent similarity engine</h3><p class="muted">11 documented similarity criteria across terrain, geology, environment and resources (plus 2 optional Earth-only operational factors); Gaussian, log-ratio and Jaccard comparisons; configurable weights; reproducible input hashes.</p></div>
      <div class="card"><h3>Honest about missing data</h3><p class="muted">Missing values never count as matches. Weight coverage is reported beside every index, and low coverage yields “Insufficient data”.</p></div>
      <div class="card"><h3>Data provenance everywhere</h3><p class="muted">Every value carries its dataset, version, method and class — <span class="cls verified">verified</span> <span class="cls derived">derived</span> <span class="cls demo">demo</span>.</p></div>
      <div class="card"><h3>Planetary-aware maps</h3><p class="muted">Earth sites on an Earth map; Moon and Mars targets on their own planetocentric maps with NASA Trek imagery. Coordinates are never mixed.</p></div>
      <div class="card"><h3>Data Center</h3><p class="muted">Upload, inspect, map fields, validate, process, version and activate datasets without touching code. GeoTIFF DEMs are processed server-side with windowed reads.</p></div>
      <div class="card"><h3>Comparison lab &amp; reports</h3><p class="muted">Compare three candidates side by side, export CSV, and generate PDF reports with methods, citations and limitations.</p></div>
    </div>
  </section>

  <section class="section">
    <h2>Candidate locations</h2>
    <p class="sub">Candidates are examples to evaluate, not predetermined winners.</p>
    <div class="grid g4">${sites.slice(0, 12).map(s => `<a class="sitechip" href="#/site/${encodeURIComponent(s.id)}"><b>${esc(s.name)}</b><small>${esc(s.country || '')} · ${s.categories.map(c => esc(CAT_LABEL[c] || c)).join(', ')}</small></a>`).join('')}</div>
    <p style="margin-top:12px"><a href="#/catalogue">Full catalogue (${sites.length}) →</a></p>
  </section>

  <section class="section">
    <h2>Data transparency</h2>
    <div class="grid g4">
      <div class="card kpi"><span class="v">${byClass('verified')}</span><span class="l">${cls('verified')} active datasets</span></div>
      <div class="card kpi"><span class="v">${byClass('demo')}</span><span class="l">${cls('demo')} active datasets</span></div>
      <div class="card kpi"><span class="v">${byClass('reference')}</span><span class="l">${cls('reference')} catalogue / imagery</span></div>
      <div class="card kpi"><span class="v">${planned}</span><span class="l"><span class="status planned">planned</span> NASA products</span></div>
    </div>
    <p class="small muted" style="margin-top:10px">Planned products (e.g. NASADEM, MODIS LST, LRO LOLA, MGS MOLA) are listed with their sources but are <b>not</b> used in any score until imported. <a href="#/data">See the dataset catalogue →</a></p>
  </section>

  <section class="section">
    <h2>Credits</h2>
    <p class="muted">Built by team <b>PLANEX</b> for the NASA Space Apps Challenge 2026. Basemaps: NASA Solar System Treks (LRO WAC, LOLA, Viking MDIM 2.1, MOLA), NASA GIBS Blue Marble, Natural Earth. Mapping with Leaflet. EarthTwin is independent and not endorsed by NASA. <a href="#/about">About the project →</a></p>
  </section>`;
  const m = await earthMap($('#pmap'), { compact: true });
  m.setSites(sites, id => { location.hash = `#/site/${encodeURIComponent(id)}`; });
  return { destroy() { m.map.remove(); } };
}
