export async function render(main) {
  main.innerHTML = `
  <div class="prose">
    <h1 style="font-size:1.9rem">About EarthTwin</h1>
    <p class="muted" style="font-size:1.05rem">EarthTwin is a scientific decision-support prototype built by team <b>PLANEX</b> for the NASA Space Apps Challenge 2026, challenge <em>“Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars”</em>.</p>
    <h2>Purpose</h2>
    <p>Mission teams test rovers, drills, habitats and procedures at terrestrial analog sites before flight, but those sites are often characterised unevenly. EarthTwin helps researchers answer four questions: which Earth locations share relevant characteristics with a chosen lunar or Martian region; what measured evidence supports each match; how similar the environments are and where they differ; and which locations may suit equipment testing, terrain navigation or geological investigation.</p>
    <h2>Technical approach</h2>
    <ul>
      <li><b>Backend:</b> Python · FastAPI · SQLite (schema in plain SQL migrations) · rasterio/pyproj for GeoTIFF processing and planetary CRSs · reportlab for PDF reports.</li>
      <li><b>Frontend:</b> dependency-light vanilla JavaScript modules, Leaflet maps, inline-SVG charts — no build step.</li>
      <li><b>Data model:</b> target worlds and regions, Earth analog sites, datasets and versions, observations, similarity criteria and assessments, data-quality assessments, citations, analysis jobs, map layers and exported reports.</li>
      <li><b>Pipeline:</b> every dataset — including the shipped demonstration data — enters through the same import, validation and processing path the Data Center exposes.</li>
    </ul>
    <h2>Acknowledgments</h2>
    <p>Basemap imagery: NASA Solar System Treks (LRO WAC mosaic, LRO LOLA shaded relief, Viking MDIM 2.1, MGS MOLA shaded relief) and NASA GIBS (Blue Marble). Land outlines: Natural Earth (public domain). Dataset metadata search: NASA Common Metadata Repository. Mapping library: Leaflet (BSD-2-Clause). Scientific sources are listed on the <a href="#/methodology">Methodology</a> page.</p>
    <h2>Limitations</h2>
    <p>EarthTwin currently ships with <b>demonstration measurements</b> that are illustrative placeholders. Until verified datasets are imported, its indices demonstrate the method, not scientific conclusions. The similarity index is a prototype that has not been validated against expert site assessments. See the full list on the <a href="#/methodology">Methodology</a> page.</p>
    <h2>Independence</h2>
    <p>EarthTwin is an independent team project created for the NASA Space Apps Challenge. It is not affiliated with, endorsed by or an official product of NASA or any other agency or institution. The use of NASA data and imagery does not imply endorsement.</p>
    <h2>Team</h2>
    <p>Team PLANEX. Contributor names are maintained by the team in the repository README.</p>
  </div>`;
}
