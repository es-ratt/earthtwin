# EarthTwin: missing data report

Team PLANEX · NASA Space Apps 2026 · updated 2026-11-11 after working through *EarthTwin Data Still Needed* (PDF)

No SAMPLE data is left. Remaining gaps are **empty** (`"value": null, "status": "TODO"`, with the reason) or
**unconfirmed** (`status: "verify"`, until a second person checks them). Every new value has a source.

## 1. Done in this round

| Item | Result | Source |
|---|---|---|
| Positions for 5 Moon targets | Peak near Cabeus B −83.6°, 291.2°E · Mons Mouton Plateau −84.3°, 30.6°E · Nobile Rim 1 and Mons Mouton (shared) −85.4°, 35.3°E · Nobile Rim 2 −83.9°, 58.7°E. All `verify`, `kind: roi_centre`. Values match the PDF. | LROC NAC ROI product pages |
| Slope, roughness (240 m), highest sun angle | Computed at those 5 positions. These targets now score all 18 Earth sites (before: 15 "Cannot be evaluated"). | LOLA LDEM_75S_240M; NSSDC Moon fact sheet |
| Positions for Arcadia, Utopia, Phlegra | 49.02°N 188.15°E · 46.74°N 117.52°E · 40.40°N 163.71°E, `kind: region_centre`, **not sampled** (PDF warning 4). | USGS Gazetteer features 348, 6260, 4701 |
| Moon annual max / mean temperature, ice-stability area and depth | 9 Moon targets, context only (not scored). | LRO Diviner PRP, PDS (model output) |
| Geologic map units | 9 Moon targets, plus AP-105, Deuteronilus and Erebus; context only. | USGS Unified Geologic Map of the Moon; USGS SIM 3292 |
| PSR mean annual maximum (Section 2.1) | Haworth 75 K, de Gerlache 94 K, Malapert 103 K, Nobile 107 K (Rim 1 and 2), Cabeus 95 K, as a separate feature `psr_mean_annual_max_K`. `verify`. | Team doc citing Hayne et al. 2015 |
| Nobile Rim 2 and Slater Plain geology (Section 2.1) | Stored as `geologic_unit_paper`; `geology_type` stays empty, because a unit is not a rock type. | EPSC 2024-473; LPSC 2025 #2401 |
| SkyFall constraints | Checked against the NASA package. TBD: the 100 m slope limit and the southern latitude limit. Not TBD: elevation, rock cover, thermal inertia, ellipse. Latitude constraint added. Still `verify`. | SkyFall Mission Information Package, section V |
| SkyFall dates | 2028 launch, ~2-year trajectory; Landing Site Workshop 1 is 9–10 Feb 2027. | Same package |
| Logistics re-run | Road distance now exists for 6 of 18 sites (was 3). | OpenStreetMap (still overloaded) |

## 2. Conflicts found (team must decide)

1. **Arcadia Planitia centre:** the PDF's value is 47.2°N, 184.3°E (from a Wikipedia mirror). The USGS Gazetteer gives **49.02°N, 188.15°E**, and the Gazetteer value is used. Utopia's 47°N, 118°E is a rounded version of 46.74°N, 117.52°E.
2. **SkyFall GPR depth:** the team value is 0.5–3 m. The NASA package says ~3–5 m of penetration in low-loss materials. The scored target is unchanged.
3. **Nobile Rim 2 geology:** the EPSC abstract says Eratosthenian crater materials; the USGS 1:5M map gives pre-Nectarian crater unit (pNc) within 5 km of the LROC centre. The two use different map scales, so both are shown with their sources.

## 3. Still missing

| Item | Where | What is needed |
|---|---|---|
| **Slater Plain position** | Moon | A source for the region centre. LPSC #2401 gives only Slater crater (88°S, 111°E). |
| **Mars sampling boxes** (decision 3) | Arcadia, Utopia, Phlegra | Boxes inside 30–45°N, then `fetch_real_data.py mars` |
| **Moon temperature swing** | All 10 Moon targets | The Diviner PRP has no minimum temperature. The Diviner seasonal polar product (PCP) would be needed. |
| Moon ground ice level / depth to ice (scored) | 8–9 Moon targets | Decision: is the Diviner ice-stability depth acceptable as "depth to ice"? (It is a model of where ice could survive, not detected ice.) |
| Rock type (`geology_type`) | Haworth, Nobile Rim 2, Cabeus, Slater; AP-105, Arcadia, Utopia, Erebus | A mapping from geologic unit to rock type, with a source. |
| Rock cover | All Moon targets; all 18 Earth sites | Team decision: choose a source, or drop the feature. |
| Earth thermal inertia | 18 / 18 | Earthdata account, then `fetch_earthdata.py ati` |
| Earth road distance and access score | 12 / 18 | Re-run `fetch_context_data.py logistics` when Overpass recovers, or use NASA SEDAC gROADS (login). |
| Earth regolith type | 10 / 18 | Rules for Cambisols, Podzols and Mollisols; another soil source for McMurdo, Beacon Valley, Tso Kar and Lonar |
| Earth rock type | Nain | Rule decision for "undivided gneissic rocks" |
| Artemis HLS slope limit | Mission | A NASA source. NTRS 20250011660 (the 13 → 9 region downselect) is the place to look. |

## 4. Team decisions (from the PDF, Section 6)

1. **Coordinate convention.** Haworth and de Gerlache still use crater centres; their LROC ROI centres (−86.7°, 336.3°E and −88.5°, 293.3°E) are in the notes.
2. **Nobile Rim 1 and Mons Mouton.** They share one LROC mosaic and so have identical values. Merge them, or find separate centres (LPSC 2025 #2742, #2655).
3. **Mars sampling.** Region centres are not sampled; boxes inside 30–45°N are needed.
4. **Rock cover.** Pick a source or proxy, or drop it from the score.
5. **Soil categories** and "undivided gneissic rocks".
6. **NASA-TBD flags.** Answered from the NASA package (see Section 1); a second person still needs to check them.

## 5. Notes on the data documents (Section 5 of the PDF)

These are already flagged in the app. The fixes belong in the team document.

- **Shackleton facts.** The crater count, boulder count and radiation dose carry `no_specific_source`. The Shackleton temperatures carry `inconsistent_in_docs`.
- **Minimum temperatures and the tracking link.** The "−246 °C / −233 °C" minimum temperatures and the `?utm_source=chatgpt.com` link are not in the app data.
- **Haworth <40 K.** This value comes from Wikipedia and is shown only as a conflict note.
