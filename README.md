# 🌍 EarthTwin

**Where on Earth is the Moon and Mars?**
EarthTwin finds Earth locations that closely match Moon and Mars mission targets, and ranks them with an explainable score.

**Team PLANEX | NASA Space Apps Challenge**
**Challenge:** Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars

🔗 **Live demo:** https://es-ratt.github.io/earthtwin/

---

## 📌 Overview

Before going to the Moon or Mars, engineers test rovers, ice drills, habitats, and crew operations in places on Earth that feel similar. Choosing those places is slow and manual, and the data is spread across many sources.

EarthTwin makes it simple:
- Pick a mission and a Moon or Mars target
- Set what matters most (terrain, geology, environment, resources)
- Get a ranked list of Earth analog sites with a clear reason for every score

---

## ✨ Features

- 🎯 **Mission setup wizard:** 4 mission types, 4 targets, 4 priority presets plus custom sliders
- 🔍 **Earth Scan:** ranks candidate sites by Analog Match Index (AMI) and confidence
- 🗺️ **Interactive map:** ranked markers, click to select
- 📄 **Site profiles:** strengths, limitations, and potential applications
- 💡 **Explainable scores:** plain-language "Why did this site score X%?"
- ⚖️ **Site comparison:** compare up to 3 sites side by side
- 📅 **Seasonal analysis:** monthly chart and best testing window
- 🧾 **Mission report:** print or save as PDF, or download as HTML
- 🌗 **Light and dark theme**, mobile friendly, keyboard accessible

---

## 🧭 How It Works

| Step | What happens |
|------|--------------|
| 1. Choose mission | Permanent Base, Landing Site, Rover Testing, or Research Mission |
| 2. Choose target | Lunar South Pole, Mare Tranquillitatis, Mars Landing Zone, or Arcadia Planitia |
| 3. Set priorities | Use a preset or custom weights (always total 100%) |
| 4. Scan Earth | Every candidate site is scored against the target |
| 5. Explore | Map, profiles, comparison, seasons, and report |

---

## 🌕 Targets

| Target | Body | Environment | Key characteristics |
|--------|------|-------------|---------------------|
| Lunar South Pole | Moon | Extreme cold, permanent shadow, changing illumination | Shadowed ice, highland anorthosite, high resource potential |
| Mare Tranquillitatis | Moon | Basaltic plain, large day-night thermal swing | Low slope, basalt mare, ilmenite |
| Mars Landing Zone | Mars | Dusty basaltic plain, thin CO₂ atmosphere | Basalt, clay and delta deposits, moderate resources |
| Arcadia Planitia | Mars | Mid-latitude ice plains, cold, smooth | Shallow subsurface ice, volcanic plains |

---

## 📐 Scoring Model

Each Earth site gets a similarity score (0 to 100) for four factors:

| Factor | What it compares |
|--------|------------------|
| Terrain | Elevation, slope, roughness |
| Geology | Rock and soil type (basalt, sediments, minerals) |
| Environment | Temperature, cold conditions, aridity |
| Resources | Ground ice, water, and useful minerals |

**Analog Match Index (AMI)**
```
AMI = (Terrain × wT + Geology × wG + Environment × wE + Resources × wR) / 100
```
Weights `w` come from the preset or the sliders and always add up to 100%.

**Confidence**
```
Confidence = site data confidence − 0.3 × spread between the four factor scores
```
Confidence goes down when the factors disagree strongly. It is a heuristic, not a statistical probability.

**Priority presets**

| Preset | Terrain | Geology | Environment | Resources | Best for |
|--------|:------:|:-------:|:-----------:|:---------:|----------|
| General Analog | 25% | 20% | 25% | 30% | Balanced search |
| Rover Testing | 40% | 30% | 20% | 10% | Mobility and slopes |
| Ice Drill Testing | 15% | 15% | 25% | 45% | Ground ice and cold |
| Habitat Materials | 20% | 45% | 25% | 10% | Regolith and rock |

**Mission type to default preset**

| Mission | Default preset |
|---------|----------------|
| Permanent Base | Ice Drill Testing |
| Landing Site | Rover Testing |
| Rover Testing | Rover Testing |
| Research Mission | General Analog |

---

## 🌐 Candidate Earth Sites (12)

| # | Site | Country | Lat, Lon | Why it is a candidate |
|---|------|---------|----------|-----------------------|
| 1 | Antarctic Dry Valleys | Antarctica | -77.5, 161.0 | Hyper-arid cold desert, buried ground ice |
| 2 | High Arctic Permafrost | Canada (Nunavut) | 75.4, -89.0 | Impact crater terrain, permafrost |
| 3 | Svalbard Valley Systems | Norway | 78.2, 16.0 | Glacial valleys, periglacial landforms |
| 4 | Icelandic Volcanic Fields | Iceland | 64.9, -19.0 | Fresh basalt, ice-volcano interaction |
| 5 | Iceland Lava Tubes | Iceland | 64.7, -20.5 | Lava-tube habitat analogs, ice-bearing caves |
| 6 | Hawaiian Basalt Fields | USA (Hawaii) | 19.5, -155.5 | Well-studied basalt, mature infrastructure |
| 7 | Craters of the Moon | USA (Idaho) | 43.4, -113.5 | Young basalt flows, cinder cones, lava tubes |
| 8 | Atacama Desert | Chile | -24.5, -69.3 | Hyper-arid, oxidized salt-rich soils |
| 9 | Utah High Desert | USA (Utah) | 38.4, -110.8 | Sedimentary layers, habitat simulation heritage |
| 10 | Canary Volcanic Terrain | Spain (Tenerife) | 28.3, -16.6 | High-altitude volcanic landscape |
| 11 | Namib Gravel Plains | Namibia | -24.0, 15.5 | Flat gravel plains for landing trials |
| 12 | Danakil Depression | Ethiopia | 14.2, 40.3 | Evaporites, hydrothermal features |

---

## 🛰️ Data

### Data status in this prototype

| Data | Status in prototype | Notes |
|------|---------------------|-------|
| Target profiles (4 targets) | Illustrative | Values written to match published characteristics |
| Earth site scores (12 sites) | Illustrative | Per-factor scores for Moon and Mars are demo values |
| Ground ice, basalt, cold indices | Illustrative | 0 to 1 indicators used to adjust factor scores |
| Seasonal curves | Generated | Computed from latitude, thermal character, and weights |
| Site imagery | Placeholder | Gradient tiles, not real photos |

### NASA data sources the pipeline is designed for

| Factor | Moon target data | Mars target data | Earth site data |
|--------|------------------|------------------|-----------------|
| Terrain | LRO **LOLA** (elevation, slope) | **MOLA** (elevation, slope) | **SRTM** / ASTER GDEM (elevation, slope) |
| Terrain (roughness) | LRO **LROC** imagery | **HiRISE** / **CTX** imagery | Landsat imagery |
| Geology | LRO / Clementine mineral maps | **CRISM** / **OMEGA** mineral maps | **ASTER** / Landsat mineralogy |
| Environment | LRO **Diviner** (temperature, shadow) | **THEMIS** (temperature), **MCS** (dust and atmosphere) | **MODIS** (land surface temperature, snow, vegetation), **MERRA-2** / **GPM** (climate, rainfall) |
| Resources | **LCROSS**, **LEND**, Lunar Prospector (water ice, hydrogen) | **GRS**, **SHARAD**, **MARSIS** (subsurface ice) | **SMAP** (soil moisture), ground-ice and permafrost maps |

Data portals: [NASA Earthdata](https://earthdata.nasa.gov) and [NASA PDS](https://pds.nasa.gov)

### Minimum data set for the next version

| Body | Datasets |
|------|----------|
| Moon | LOLA + Diviner |
| Mars | MOLA + THEMIS |
| Earth | SRTM + MODIS + ASTER |

These cover all four factors.

---

## 🛠️ Tech Stack

| Part | Choice |
|------|--------|
| Frontend | HTML, CSS, vanilla JavaScript (single file) |
| Map | Inline SVG schematic world map |
| Charts | Inline SVG |
| Hosting | GitHub Pages |
| Dependencies | None, no build step |

---

## 🚀 Run Locally

```bash
git clone https://github.com/es-ratt/earthtwin.git
cd earthtwin
```
Then open `index.html` in any modern browser.

---

## 📁 Project Structure

```
earthtwin/
├── index.html   # complete app (UI, scoring, data, charts)
└── README.md
```

---

## ⚠️ Limitations

- Earth cannot reproduce lunar or Martian **gravity, vacuum, atmosphere, or radiation**. Every site profile says so.
- This is a **frontend prototype using illustrative data**. Results are not scientific mission recommendations and are not validated NASA analysis.
- Confidence is a demo heuristic, not a statistical probability.
- The map is schematic, not geographically exact.

---

## 🔮 Roadmap

- [ ] Replace illustrative values with real NASA dataset values (LOLA, Diviner, MOLA, THEMIS, SRTM, MODIS, ASTER)
- [ ] Add real site imagery
- [ ] Expand beyond 12 sites and add more lunar and Martian targets
- [ ] Add a proper map with real coordinates and layers
- [ ] Validate scoring with planetary science references

---

## 👥 Team PLANEX

Built for the NASA Space Apps Challenge.

**Disclaimer:** EarthTwin is an independent project and is not affiliated with NASA.