#!/usr/bin/env python3
"""NASA Earthdata products that need a (free) Earthdata login: ATI thermal-inertia proxy and ASTER GDEM v3.

    python pipeline/fetch_earthdata.py ati                 # AppEEARS point request: MYD11A1 + MCD43A3 → ATI proxy
    python pipeline/fetch_earthdata.py ati --from-csv DIR  # same, from AppEEARS CSVs you downloaded in the browser
    python pipeline/fetch_earthdata.py aster-dem           # earthaccess: ASTGTM v003 tiles for sites above 60° latitude
    add --only id1,id2 to limit the candidates

Login (never typed into this script, never printed):
  put your Earthdata credentials in ~/.netrc:
      machine urs.earthdata.nasa.gov login <your user name> password <your password>
  then `chmod 600 ~/.netrc`. Create the account at https://urs.earthdata.nasa.gov/users/new.

Products (IDs and versions checked in NASA CMR and the AppEEARS product list on 2026-11-10):
  MYD11A1.061  Aqua MODIS LST & emissivity, daily, 1 km   (C1748046084-LPCLOUD)  layers LST_Day_1km, LST_Night_1km, QC_Day, QC_Night
  MCD43A3.061  MODIS BRDF/albedo, daily (16-day window), 500 m (C2278860820-LPCLOUD) layers Albedo_WSA_shortwave,
               BRDF_Albedo_Band_Mandatory_Quality_shortwave
  ASTGTM.003   ASTER GDEM v3, 1 arc-second               (C1711961296-LPCLOUD)

ATI (apparent thermal inertia) = (1 − albedo) / (LST_day − LST_night), per day with good-quality values on both,
then the median over the year. Unit K⁻¹. It is a PROXY: it is NOT thermal inertia in J m⁻² K⁻¹ s⁻½ and is
never compared with the Mars thermal-inertia value (different variable and unit). Shown as context only.
Aqua (13:30 / 01:30 local overpass) is used because its day/night times are closer to the daily maximum and
minimum than Terra's.

NOTE: written against the documented AppEEARS API (https://appeears.earthdatacloud.nasa.gov/api/) and the
earthaccess library, but NOT run here (no Earthdata login in this environment). Check the first run.
"""
from __future__ import annotations

import base64
import csv
import json
import netrc
import sys
import time
from pathlib import Path

import numpy as np

from common import (DATASETS, EARTH_FIELDS, MANUAL, USER_AGENT, load_candidates, parse_only, provenance, row,
                    write_csv)

APPEEARS = "https://appeears.earthdatacloud.nasa.gov/api"
URS_HOST = "urs.earthdata.nasa.gov"
ATI_YEAR = "2025"
ATI_MIN_DELTA_T_K = 2.0       # skip days with a tiny day−night difference (ATI blows up); method choice
LST_SCALE, LST_FILL = 0.02, 0
ALBEDO_SCALE, ALBEDO_FILL = 0.001, 32767
ALBEDO_GOOD_QA = {0, 1}       # 0 = full BRDF inversion, 1 = magnitude inversion
POLL_S = 30
LAYERS = [("MYD11A1.061", "LST_Day_1km"), ("MYD11A1.061", "LST_Night_1km"), ("MYD11A1.061", "QC_Day"), ("MYD11A1.061", "QC_Night"),
          ("MCD43A3.061", "Albedo_WSA_shortwave"), ("MCD43A3.061", "BRDF_Albedo_Band_Mandatory_Quality_shortwave")]


# ------------------------------------------------------------------ login
def earthdata_credentials() -> tuple[str, str]:
    try:
        auth = netrc.netrc().authenticators(URS_HOST)
    except (FileNotFoundError, netrc.NetrcParseError) as e:
        raise SystemExit(f"No usable ~/.netrc ({e}). See the header of this file for the one-line setup.") from e
    if not auth:
        raise SystemExit(f"~/.netrc has no entry for {URS_HOST}. See the header of this file.")
    return auth[0], auth[2]


def appeears_request(method: str, path: str, token: str | None = None, body: dict | None = None, basic: str | None = None):
    import urllib.request

    from common import SSL_CTX

    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if basic:
        headers["Authorization"] = f"Basic {basic}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{APPEEARS}/{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=300, context=SSL_CTX) as r:
        raw = r.read()
        return json.loads(raw) if r.headers.get_content_type() == "application/json" else raw


def appeears_login() -> str:
    user, pw = earthdata_credentials()
    basic = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return appeears_request("POST", "login", basic=basic)["token"]


# ------------------------------------------------------------------ ATI via AppEEARS
def submit_point_task(token: str, cands: list[dict]) -> str:
    body = {"task_type": "point", "task_name": f"earthtwin-ati-{ATI_YEAR}",
            "params": {"dates": [{"startDate": f"01-01-{ATI_YEAR}", "endDate": f"12-31-{ATI_YEAR}"}],
                       "layers": [{"product": p, "layer": l} for p, l in LAYERS],
                       "coordinates": [{"id": c["id"], "category": "earthtwin", "latitude": float(c["lat"]),
                                        "longitude": float(c["lon"])} for c in cands]}}
    return appeears_request("POST", "task", token=token, body=body)["task_id"]


def wait_and_download(token: str, task_id: str, out_dir: Path) -> Path:
    while True:
        status = appeears_request("GET", f"task/{task_id}", token=token).get("status")
        print(f"  AppEEARS task {task_id}: {status}")
        if status == "done":
            break
        if status in ("error", "expired"):
            raise SystemExit(f"AppEEARS task {task_id} ended with status '{status}'")
        time.sleep(POLL_S)
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in appeears_request("GET", f"bundle/{task_id}", token=token)["files"]:
        if f["file_name"].endswith(".csv"):
            (out_dir / Path(f["file_name"]).name).write_bytes(appeears_request("GET", f"bundle/{task_id}/{f['file_id']}", token=token))
    return out_dir


def read_appeears_csv(folder: Path, product: str) -> dict[str, dict[str, dict]]:
    """{site_id: {date: row}} from the AppEEARS results CSV of one product."""
    files = sorted(folder.glob(f"*{product.replace('.', '-')}-results.csv"))
    if not files:
        raise SystemExit(f"No AppEEARS results CSV for {product} in {folder}")
    out: dict[str, dict[str, dict]] = {}
    with open(files[0], encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["ID"], {})[r["Date"]] = r
    return out


def _num(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def scaled(v: float | None, scale: float, fill: float) -> float | None:
    """AppEEARS CSVs usually hold scaled values; raw integers are detected and scaled. Fill → None."""
    if v is None or v == fill or abs(v - fill * scale) < 1e-9:   # raw or already-scaled fill value
        return None
    return v * scale if v > (1000 if scale == LST_SCALE else 1.5) else v


def ati_for_site(lst: dict[str, dict], alb: dict[str, dict]) -> tuple[float | None, int]:
    p_lst, p_alb = "MYD11A1_061_", "MCD43A3_061_"
    values = []
    for d, r in lst.items():
        a = alb.get(d)
        if not a:
            continue
        qd, qn = _num(r.get(p_lst + "QC_Day")), _num(r.get(p_lst + "QC_Night"))
        if qd is None or qn is None or int(qd) & 0b11 or int(qn) & 0b11:   # bits 0–1 = 0: good quality
            continue
        day = scaled(_num(r.get(p_lst + "LST_Day_1km")), LST_SCALE, LST_FILL)
        night = scaled(_num(r.get(p_lst + "LST_Night_1km")), LST_SCALE, LST_FILL)
        albedo = scaled(_num(a.get(p_alb + "Albedo_WSA_shortwave")), ALBEDO_SCALE, ALBEDO_FILL)
        qa = _num(a.get(p_alb + "BRDF_Albedo_Band_Mandatory_Quality_shortwave"))
        if None in (day, night, albedo) or qa is None or int(qa) not in ALBEDO_GOOD_QA or day - night < ATI_MIN_DELTA_T_K:
            continue
        values.append((1.0 - albedo) / (day - night))
    return (float(np.median(values)) if values else None), len(values)


def run_ati(only: list[str] | None, from_csv: Path | None) -> None:
    cands = load_candidates(only)
    folder = from_csv
    if folder is None:
        token = appeears_login()
        task = submit_point_task(token, cands)
        folder = wait_and_download(token, task, MANUAL / "appeears" / task)
    lst, alb = read_appeears_csv(folder, "MYD11A1-061"), read_appeears_csv(folder, "MCD43A3-061")
    prov = provenance("NASA MODIS Aqua LST (MYD11A1) + MODIS BRDF/Albedo (MCD43A3) via AppEEARS", "MYD11A1 + MCD43A3", "061",
                      f"{ATI_YEAR}-01-01 to {ATI_YEAR}-12-31 (daily)", "LST 1 km; albedo 500 m (AppEEARS point = containing pixel)",
                      f"Per day: QC bits 0–1 = 0 on day and night LST, albedo QA in {sorted(ALBEDO_GOOD_QA)}, day − night ≥ "
                      f"{ATI_MIN_DELTA_T_K} K; ATI = (1 − white-sky shortwave albedo) / (LST_day − LST_night); median over days",
                      "https://appeears.earthdatacloud.nasa.gov/")
    rows = []
    for c in cands:
        ati, n = ati_for_site(lst.get(c["id"], {}), alb.get(c["id"], {}))
        polar = abs(float(c["lat"])) > 60
        conf = "low" if polar or n < 20 else "medium"
        note = (f"PROXY in K⁻¹, NOT thermal inertia in J m⁻² K⁻¹ s⁻½; not compared with Mars. {n} usable days."
                + (" Above 60° latitude day/night passes and polar night bias ΔT." if polar else ""))
        rows.append(row("candidate_id", c["id"], "ati_proxy", None if ati is None else round(ati, 5), "K⁻¹", "appeears-myd11a1-mcd43a3",
                        conf, prov, note if ati is not None else f"No usable day with good LST and albedo ({n})."))
        print(f"  {c['name'][:36]:36s} ATI={rows[-1]['value'] or 'TODO'}  ({n} days)")
    write_csv(DATASETS / "earth_features.csv", EARTH_FIELDS, rows, key=("candidate_id", "feature"))


# ------------------------------------------------------------------ ASTER GDEM v3 via earthaccess
def run_aster_dem(only: list[str] | None, min_abs_lat: float = 60.0) -> None:
    try:
        import earthaccess
    except ImportError as e:
        raise SystemExit("Install earthaccess first:  .venv/bin/pip install earthaccess") from e
    import rasterio

    from fetch_real_data import terrain_rows

    earthaccess.login(strategy="netrc")
    cands = [c for c in load_candidates(only) if abs(float(c["lat"])) > min_abs_lat]
    rows = []
    for c in cands:
        lat, lon = float(c["lat"]), float(c["lon"])
        res = earthaccess.search_data(short_name="ASTGTM", version="003", bounding_box=(lon - 0.2, lat - 0.2, lon + 0.2, lat + 0.2))
        if not res:
            print(f"  {c['id']}: no ASTGTM granule", file=sys.stderr)
            continue
        files = earthaccess.download(res, local_path=str(MANUAL / "astgtm"))
        dems = [Path(f) for f in files if str(f).endswith("_dem.tif")]
        if not dems:
            print(f"  {c['id']}: downloaded granules contain no *_dem.tif", file=sys.stderr)
            continue
        with rasterio.open(dems[0]) as ds:
            def prov_for(steps: str, name=dems[0].name) -> dict:
                return provenance("ASTER Global DEM v3 (NASA/METI) via NASA Earthdata (earthaccess)", f"ASTGTM granule {name}", "003",
                                  "ASTER stereo pairs 2000–2013", "1 arc-second (~30 m)", steps,
                                  "https://doi.org/10.5067/ASTER/ASTGTM.003")
            got = terrain_rows(c, ds, "lpdaac-astgtm-v003", "medium", "ASTER GDEM v3 (NASA/METI); replaces Copernicus above 60°", prov_for)
        rows += got
        print(f"  {c['name'][:36]:36s} " + ", ".join(f"{r['feature']}={r['value']}" for r in got))
    write_csv(DATASETS / "earth_features.csv", EARTH_FIELDS, rows, key=("candidate_id", "feature"))


def main(argv: list[str]) -> int:
    what = argv[1] if len(argv) > 1 else ""
    only = parse_only(argv)
    if what == "ati":
        run_ati(only, Path(argv[argv.index("--from-csv") + 1]) if "--from-csv" in argv else None)
    elif what == "aster-dem":
        run_aster_dem(only)
    else:
        print(__doc__)
        return 2
    print("Now run: python3 pipeline/compute_scores.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
