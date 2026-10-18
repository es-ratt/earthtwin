import * as api from '../api.js';
import { citeList, cls, esc, safeUrl, status } from '../ui.js';

export async function render(main) {
  const [vocab, cits, datasets] = await Promise.all([api.get('/api/vocabulary'), api.get('/api/citations'), api.get('/api/datasets')]);
  const th = vocab.thresholds;
  const fams = ['terrain', 'geology', 'environment', 'resources', 'operational'];
  const sec = [['analog', 'Analog ≠ equivalent'], ['pipeline', 'Data pipeline'], ['criteria', 'Criteria'], ['normalisation', 'Normalisation & units'],
    ['scoring', 'Similarity scoring'], ['weights', 'Weights & profiles'], ['missing', 'Missing data & coverage'], ['quality', 'Data classes & quality'],
    ['coords', 'Coordinate systems'], ['repro', 'Reproducibility'], ['limits', 'Limitations'], ['sources', 'Data sources'], ['refs', 'Citations']];
  main.innerHTML = `
  <div class="phead"><div><h1 style="font-size:1.7rem">Methodology &amp; data sources</h1><p>How EarthTwin turns datasets into similarity indices — and what those indices do not mean. Engine version <code>${esc(vocab.engine_version)}</code>.</p></div></div>
  <div class="twocol"><nav class="toc" aria-label="On this page">${sec.map(([k, l]) => `<a href="#/methodology" data-jump="${k}">${l}</a>`).join('')}</nav>
  <article class="prose">
    <h2 id="analog">An analog is not an equivalent</h2>
    <p>A terrestrial analog shares <em>selected</em> characteristics with a target region on the Moon or Mars. No location on Earth reproduces lunar gravity (1.62 m/s²) or Martian gravity (3.71 m/s²), lunar vacuum or the thin Martian CO₂ atmosphere, or the surface radiation environment of either body. EarthTwin therefore reports <b>which criteria agree, which differ and which lack data</b>, and labels its output a <b>prototype similarity index</b>. It is not a probability of mission success, not a validated scientific ranking and not proof of environmental equivalence.</p>

    <h2 id="pipeline">Data pipeline</h2>
    <p>Dataset import → format detection (content sniffing) → validation → metadata and field mapping (user-confirmed) → unit and coordinate normalisation → scientific processing (e.g. DEM terrain statistics) → feature extraction → database update with provenance → data-revision bump → automatic refresh of every page. Each import is stored as a dataset version with its file hash, field mapping, processing history and data-quality assessment.</p>

    <h2 id="criteria">Criteria</h2>
    <p>Criteria compare one variable measured for the Earth site with the same variable for the target region. Operational factors are Earth-only suitability attributes; they are <b>not</b> similarity measures and default to weight 0.</p>
    ${fams.map(f => `<h3>${f}</h3><div class="tablewrap"><table><thead><tr><th>Criterion</th><th>Variable</th><th>Method</th><th>Rationale</th></tr></thead><tbody>
      ${vocab.criteria.filter(c => c.family === f).map(c => `<tr><td><b>${esc(c.name)}</b></td><td><code>${esc(c.variable_key)}</code></td><td class="small">${esc(c.description)}</td><td class="small muted">${esc(c.rationale)}</td></tr>`).join('')}</tbody></table></div>`).join('')}
    <p class="small muted">Mean elevation is recorded but never scored: absolute elevations are referenced to different datums (geoid, lunar sphere, Martian areoid) and are not comparable between bodies.</p>

    <h2 id="normalisation">Normalisation &amp; units</h2>
    <p>Every numeric variable has a canonical unit (m, deg, K, mm/yr, fraction). Imported values are converted with exact factors only (e.g. km→m, °C→K, rad→deg, % grade→deg via arctan). Temperature <em>ranges</em> are converted without offset (10 °C of range = 10 K). Units are <b>required</b> for every numeric column; header-based suggestions are shown for confirmation and never applied silently. Physically implausible values (slopes outside 0–90°, negative relief, vegetation fraction outside 0–1) are rejected with a row-level error. Lithology uses a controlled vocabulary: ${vocab.lithology_terms.map(t => `<code>${esc(t)}</code>`).join(' ')}.</p>

    <h2 id="scoring">Similarity scoring</h2>
    <div class="formula">Gaussian:        s = exp(−½ · ((a − b) / σ)²)
Log ratio:       s = exp(−½ · (log10(a / b) / σ)²)
Log(1+x):        s = exp(−½ · ((log10(1+a) − log10(1+b)) / σ)²)
Jaccard (sets):  s = |A ∩ B| / |A ∪ B|
Boolean:         s = 1 if a = b else 0

Index = 100 · Σ wᵢ sᵢ / Σ wᵢ      (sum over criteria with data on both sides)
Coverage = Σ wᵢ(available) / Σ wᵢ(requested)</div>
    <p>The scale σ for each criterion is listed above; it is a documented design choice, not a fitted parameter. A criterion's <em>contribution</em> is 100·wᵢsᵢ/Σw, so contributions sum to the index.</p>

    <h2 id="weights">Weights &amp; profiles</h2>
    <p>Weights are relative (the index is a weighted mean). Mission profiles provide starting points and can be edited freely in the Explorer:</p>
    <div class="tablewrap"><table><thead><tr><th>Profile</th>${vocab.criteria.map(c => `<th class="num" title="${esc(c.name)}">${esc(c.key)}</th>`).join('')}</tr></thead><tbody>
    ${Object.entries(vocab.profiles).map(([k, p]) => `<tr><td><b>${esc(p.name)}</b><br><span class="small dim">${esc(p.description)}</span></td>${vocab.criteria.map(c => `<td class="num">${p.weights[c.key] ?? 0}</td>`).join('')}</tr>`).join('')}</tbody></table></div>

    <h2 id="missing">Missing data &amp; coverage</h2>
    <p>A missing value on either side produces no similarity and is excluded — it never counts as a match or as zero. Coverage is reported separately from similarity. If weight coverage is below <b>${Math.round(th.min_coverage * 100)}%</b> or fewer than <b>${th.min_criteria}</b> weighted criteria have data, the result is <b>“Insufficient data”</b> and no index is shown. Thresholds are configurable (<code>EARTHTWIN_MIN_COVERAGE</code>, <code>EARTHTWIN_MIN_CRITERIA</code>).</p>

    <h2 id="quality">Data classes &amp; evidence quality</h2>
    <ul><li>${cls('verified')} value from an identified dataset imported by the team (publisher and source URL or identifier required).</li>
      <li>${cls('derived')} calculated by the EarthTwin pipeline from a verified input (e.g. slope statistics from a DEM), with method and spatial support recorded.</li>
      <li>${cls('demo')} illustrative placeholder used to exercise the application — <b>DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT</b>.</li>
      <li>${cls('reference')} catalogue or context record without measurements.</li></ul>
    <p>When several active datasets provide the same variable for the same subject, EarthTwin uses verified over derived over demo, then the most recent. Each assessment reports the lowest data class among its inputs; any result touching demo data is labelled as demo everywhere, including exports.</p>

    <h2 id="coords">Coordinate systems</h2>
    <p>Earth sites use WGS 84 geographic coordinates (EPSG:4326). Moon and Mars targets are stored as planetocentric latitude and east-positive longitude (−180…180) on the IAU 2015 reference spheres (<code>IAU_2015:30100</code>, <code>IAU_2015:49900</code>). Imports must declare their longitude convention (east −180…180, east 0…360 or west-positive 0…360) and latitude type; Mars planetographic latitudes are converted with the IAU 2000 ellipsoid. Rasters must carry or declare a CRS whose ellipsoid matches the declared body; a lunar DEM can never be applied to Earth sites, and planetary coordinates are never drawn on the Earth map.</p>
    <p>Raster windows are boxes of side 2 × the record's analysis radius (default 10 km), read with windowed I/O and decimated by averaging if larger than ${'4'} million pixels. Slope uses central differences with pixel spacing in metres (from the projected CRS, or from the body radius for geographic rasters). Windows with fewer than 50% valid pixels produce no value.</p>

    <h2 id="repro">Reproducibility</h2>
    <p>Every assessment stores the weights, thresholds, engine version, the criterion-level results and an input hash over the exact observation identifiers and values used. Re-running with the same inputs yields the same hash and result; exports reference assessment IDs.</p>

    <h2 id="limits">Limitations</h2>
    <ul><li>The criteria capture a small part of what makes an analog useful (no radiation, gravity, atmospheric pressure, regolith geotechnics or illumination geometry yet).</li>
      <li>Window means hide extremes: a lunar cold trap at ~40 K and an illuminated rim near 200 K average differently than either location.</li>
      <li>Terrain statistics depend on DEM resolution and window size; compare values derived at similar resolutions.</li>
      <li>Similarity scales σ are expert choices awaiting validation against planetary-science literature.</li>
      <li>The demonstration measurements shipped with the prototype are placeholders and must be replaced with verified data before drawing conclusions.</li></ul>

    <h2 id="sources">Data sources in this installation</h2>
    <div class="tablewrap"><table><thead><tr><th>Dataset</th><th>Class</th><th>Status</th><th>Publisher</th><th>Source</th></tr></thead><tbody>
    ${datasets.map(d => `<tr><td>${esc(d.name)}</td><td>${cls(d.data_class)}</td><td>${status(d.status)}${d.active ? '' : ' <span class="dim small">inactive</span>'}</td><td class="small">${esc(d.publisher || '')}</td><td class="small">${safeUrl(d.source_url) ? `<a href="${safeUrl(d.source_url)}" target="_blank" rel="noopener">link ↗</a>` : ''}</td></tr>`).join('')}</tbody></table></div>
    <h2 id="refs">Citations recorded in the database</h2>
    <p class="small muted">“link checked” means the DOI/URL was confirmed to resolve when the record was created; the team should still verify how each source supports the stated context.</p>
    ${citeList(cits)}
  </article></div>`;
  main.querySelectorAll('[data-jump]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); document.getElementById(a.dataset.jump)?.scrollIntoView({ behavior: 'smooth' }); }));
}
