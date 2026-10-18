"""EarthTwin API + static frontend.

Interactive API documentation is served at /api/docs (OpenAPI).
Mutating Data Center operations require the `X-Admin-Token` header.
"""
from __future__ import annotations

import hmac
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .config import get_settings
from .ingest import detect as D
from .ingest import mapping as M
from .ingest import pipeline as P
from .ingest.adapters.raster import RASTER_KINDS
from .seed import seed_bundles, seed_static
from .services import analysis as A
from .services import catalog as C
from .services import exports as X
from .services import providers as PR
from .services import vocabulary as V
from .services.similarity import ENGINE_VERSION

log = logging.getLogger("earthtwin")


def init_app_state() -> None:
    s = get_settings()
    s.ensure_dirs()
    conn = db.connect()
    try:
        applied = db.migrate(conn)
        if applied:
            log.info("Applied migrations: %s", applied)
        V.sync_to_db(conn)
        seed_static(conn)
        conn.commit()
    finally:
        conn.close()
    if s.seed_demo:
        done = seed_bundles()
        if done:
            log.info("Seeded bundles: %s", done)


@asynccontextmanager
async def lifespan(_app):
    init_app_state()
    yield


app = FastAPI(title="EarthTwin API", version=ENGINE_VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan,
              description="Earth analog discovery for Moon and Mars targets — NASA Space Apps Challenge, team PLANEX.")


def conn_dep():
    with db.session() as conn:
        yield conn


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    token = get_settings().admin_token
    if not token:
        raise HTTPException(503, "Administrative operations are disabled: EARTHTWIN_ADMIN_TOKEN is not configured on the server.")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, token):
        raise HTTPException(401, "A valid admin token is required for Data Center changes.")


def _404(what: str):
    raise HTTPException(404, f"{what} not found")


# ----------------------------------------------------------------------------- meta
@app.get("/api/health")
def health(conn=Depends(conn_dep)):
    return {"ok": True, "engine_version": ENGINE_VERSION, "revision": db.revision(conn)}


@app.get("/api/state")
def state(conn=Depends(conn_dep)):
    st = C.state(conn)
    st["admin_configured"] = bool(get_settings().admin_token)
    return st


@app.get("/api/vocabulary")
def vocabulary():
    d = V.as_dicts()
    d["engine_version"] = ENGINE_VERSION
    s = get_settings()
    d["thresholds"] = {"min_coverage": s.min_weight_coverage, "min_criteria": s.min_criteria}
    return d


@app.get("/api/formats")
def formats():
    from .services.units import accepted_units
    return {
        "formats": D.SUPPORTED, "unsupported_guidance": D.UNSUPPORTED_GUIDANCE, "import_kinds": M.KINDS,
        "raster_kinds": RASTER_KINDS, "longitude_conventions": M.LON_CONVENTIONS, "latitude_types": M.LAT_TYPES,
        "standard_fields": M.FIELDS, "required_fields": M.REQUIRED,
        "accepted_units": {v.key: accepted_units(v.unit_kind) for v in V.VARIABLES if v.unit_kind},
        "limits_mb": {"table": get_settings().max_table_bytes // 2**20, "raster": get_settings().max_raster_bytes // 2**20},
        "templates": sorted(p.name for p in get_settings().templates_dir.glob("*") if p.is_file()),
    }


@app.get("/api/providers")
def providers():
    return PR.PROVIDERS


@app.get("/api/providers/nasa_cmr/search")
def cmr(q: str = Query(..., min_length=2, max_length=100)):
    try:
        return {"results": PR.cmr_search(q)}
    except PR.ProviderError as e:
        raise HTTPException(502, str(e))


# ----------------------------------------------------------------------------- catalogue
@app.get("/api/worlds")
def worlds(conn=Depends(conn_dep)):
    return db.rows(conn.execute("SELECT * FROM target_world ORDER BY CASE id WHEN 'earth' THEN 0 WHEN 'moon' THEN 1 ELSE 2 END"))


@app.get("/api/targets")
def targets(world: str | None = None, q: str | None = None, include_demo: bool = True, conn=Depends(conn_dep)):
    return C.list_targets(conn, world, q, include_demo)


@app.get("/api/targets/{target_id}")
def target(target_id: str, include_demo: bool = True, conn=Depends(conn_dep)):
    return C.get_target(conn, target_id, include_demo) or _404("Target region")


@app.get("/api/sites")
def sites(q: str | None = None, category: str | None = None, include_demo: bool = True, conn=Depends(conn_dep)):
    return C.list_sites(conn, q, category, include_demo)


@app.get("/api/sites/{site_id}")
def site(site_id: str, include_demo: bool = True, conn=Depends(conn_dep)):
    return C.get_site(conn, site_id, include_demo) or _404("Earth site")


@app.get("/api/citations")
def citations(conn=Depends(conn_dep)):
    return db.rows(conn.execute(
        """SELECT c.*, d.name AS dataset_name, d.status AS dataset_status, d.active AS dataset_active
           FROM citation c LEFT JOIN dataset d ON d.id = c.dataset_id ORDER BY c.kind, c.text"""))


@app.get("/api/layers")
def layers(body: str | None = None, conn=Depends(conn_dep)):
    q = """SELECT l.id, l.dataset_id, l.name, l.body, l.kind, l.tile_url, l.legend, l.attribution, l.feature_count,
                  d.name AS dataset_name, d.data_class FROM map_layer l JOIN dataset d ON d.id = l.dataset_id WHERE d.active = 1"""
    args: list = []
    if body:
        q += " AND l.body = ?"
        args.append(body)
    out = db.rows(conn.execute(q + " ORDER BY l.kind DESC, l.name", args))
    for l in out:
        l["legend"] = db.loads(l["legend"], {})
    return out


@app.get("/api/layers/{layer_id}/geojson")
def layer_geojson(layer_id: str, conn=Depends(conn_dep)):
    r = conn.execute("SELECT geojson_path FROM map_layer WHERE id = ? AND kind = 'vector'", (layer_id,)).fetchone()
    if not r or not r[0] or not Path(r[0]).exists():
        _404("Layer")
    return FileResponse(r[0], media_type="application/geo+json")


# ----------------------------------------------------------------------------- analysis
class AnalysisRequest(BaseModel):
    target_id: str
    profile: str | None = None
    weights: dict[str, float] | None = None
    site_ids: list[str] | None = Field(default=None, max_length=200)
    include_demo: bool = True


def _run(conn, req: AnalysisRequest, persist=True):
    try:
        return A.run(conn, req.target_id, req.profile, req.weights, req.site_ids, req.include_demo, persist)
    except (A.AnalysisError, ValueError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/analysis/rank")
def rank(req: AnalysisRequest, conn=Depends(conn_dep)):
    return _run(conn, req)


@app.get("/api/assessments/{assessment_id}")
def assessment(assessment_id: str, conn=Depends(conn_dep)):
    return A.get_assessment(conn, assessment_id) or _404("Assessment")


def _req_from_query(target_id, profile, weights, site_ids, include_demo) -> AnalysisRequest:
    try:
        w = json.loads(weights) if weights else None
    except ValueError:
        raise HTTPException(400, "weights must be JSON")
    ids = [s for s in site_ids.split(",") if s] if site_ids else None
    return AnalysisRequest(target_id=target_id, profile=profile, weights=w, site_ids=ids, include_demo=include_demo)


@app.get("/api/export/candidates.csv")
def export_candidates(target_id: str, profile: str | None = None, weights: str | None = None, include_demo: bool = True, conn=Depends(conn_dep)):
    res = _run(conn, _req_from_query(target_id, profile, weights, None, include_demo))
    text = X.candidates_csv(conn, res)
    return Response(text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="earthtwin-candidates-{target_id}.csv"'})


@app.get("/api/export/comparison.csv")
def export_comparison(target_id: str, site_ids: str, profile: str | None = None, weights: str | None = None,
                      include_demo: bool = True, conn=Depends(conn_dep)):
    res = _run(conn, _req_from_query(target_id, profile, weights, site_ids, include_demo))
    text = X.comparison_csv(conn, res)
    return Response(text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="earthtwin-comparison-{target_id}.csv"'})


@app.get("/api/export/report.pdf")
def export_pdf(target_id: str, site_ids: str | None = None, profile: str | None = None, weights: str | None = None,
               include_demo: bool = True, conn=Depends(conn_dep)):
    res = _run(conn, _req_from_query(target_id, profile, weights, None, include_demo))
    tgt = C.get_target(conn, target_id, include_demo)
    detail = [s for s in (site_ids or "").split(",") if s]
    ds_ids = {o["dataset_id"] for o in tgt["observations"]}
    site_obs = C.active_observations(conn, "earth_site", [r["site"]["id"] for r in res["results"]], include_demo)
    ds_ids |= {o["dataset_id"] for o in site_obs}
    ds_ids |= {tgt["source_dataset_id"]}
    datasets = [d for d in C.list_datasets(conn) if d["id"] in ds_ids]
    for d in datasets:
        v = conn.execute("SELECT version FROM dataset_version WHERE id = ?", (d["current_version_id"],)).fetchone()
        d["version"] = v[0] if v else ""
    cits = db.rows(conn.execute(
        f"SELECT * FROM citation WHERE dataset_id IN ({','.join('?' * len(ds_ids))}) OR (subject_type='target_region' AND subject_id=?) "
        f"OR (subject_type='earth_site' AND subject_id IN ({','.join('?' * max(1, len(detail)))}))",
        [*ds_ids, target_id, *(detail or [""])]))
    pdf = X.report_pdf(conn, res, tgt, detail, cits, datasets)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="earthtwin-report-{target_id}.pdf"'})


@app.get("/api/exports")
def exports_list(conn=Depends(conn_dep)):
    return db.rows(conn.execute("SELECT id, kind, target_region_id, created_at FROM exported_report ORDER BY created_at DESC LIMIT 50"))


# ----------------------------------------------------------------------------- data center (read)
@app.get("/api/datasets")
def datasets(conn=Depends(conn_dep)):
    return C.list_datasets(conn)


@app.get("/api/datasets/{dataset_id}")
def dataset(dataset_id: str, conn=Depends(conn_dep)):
    return C.get_dataset(conn, dataset_id) or _404("Dataset")


@app.get("/api/imports")
def imports(conn=Depends(conn_dep)):
    out = db.rows(conn.execute(
        """SELECT i.id, i.original_filename, i.size_bytes, i.detected_format, i.import_kind, i.status, i.dataset_id, i.job_id,
                  i.created_at, i.updated_at, j.error AS job_error FROM import_session i LEFT JOIN analysis_job j ON j.id = i.job_id
           ORDER BY i.created_at DESC LIMIT 100"""))
    return out


@app.get("/api/imports/{import_id}")
def import_get(import_id: str, conn=Depends(conn_dep)):
    try:
        return P.public_session(P._session(conn, import_id))
    except P.ImportError_:
        _404("Import")


@app.get("/api/jobs/{job_id}")
def job_get(job_id: str, conn=Depends(conn_dep)):
    try:
        return P.job(conn, job_id)
    except P.ImportError_:
        _404("Job")


# ----------------------------------------------------------------------------- data center (admin)
@app.post("/api/admin/check", dependencies=[Depends(require_admin)])
def admin_check():
    return {"ok": True}


@app.post("/api/imports", dependencies=[Depends(require_admin)])
def import_create(file: UploadFile = File(...), kind: str | None = Form(default=None)):
    try:
        return P.create_session(file.file, file.filename or "upload", kind)
    except P.ImportError_ as e:
        raise HTTPException(422, str(e))


class MappingRequest(BaseModel):
    kind: str
    mapping: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.put("/api/imports/{import_id}/mapping", dependencies=[Depends(require_admin)])
def import_mapping(import_id: str, req: MappingRequest):
    if req.kind not in M.KINDS:
        raise HTTPException(400, f"Unknown import kind '{req.kind}'")
    try:
        return P.set_mapping(import_id, req.kind, req.mapping, req.metadata)
    except P.ImportError_ as e:
        raise HTTPException(409, str(e))


@app.post("/api/imports/{import_id}/propose", dependencies=[Depends(require_admin)])
def import_propose(import_id: str, kind: str = Query(...), conn=Depends(conn_dep)):
    try:
        s = P._session(conn, import_id)
    except P.ImportError_:
        _404("Import")
    return P.propose_for(kind, s["structure"])


@app.post("/api/imports/{import_id}/process", dependencies=[Depends(require_admin)])
def import_process(import_id: str):
    try:
        return P.start_processing(import_id)
    except P.ImportError_ as e:
        raise HTTPException(409, str(e))


class DatasetPatch(BaseModel):
    name: str | None = None
    identifier: str | None = None
    publisher: str | None = None
    source_url: str | None = None
    license: str | None = None
    description: str | None = None
    provenance: str | None = None
    spatial_resolution: str | None = None
    temporal_coverage: str | None = None
    crs: str | None = None


@app.patch("/api/datasets/{dataset_id}", dependencies=[Depends(require_admin)])
def dataset_patch(dataset_id: str, patch: DatasetPatch, conn=Depends(conn_dep)):
    d = conn.execute("SELECT data_class FROM dataset WHERE id = ?", (dataset_id,)).fetchone()
    if not d:
        _404("Dataset")
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if d[0] == "verified" and ("publisher" in fields and not fields["publisher"].strip()):
        raise HTTPException(400, "Verified datasets must keep a publisher")
    if fields:
        conn.execute(f"UPDATE dataset SET {', '.join(f'{k}=?' for k in fields)}, updated_at=? WHERE id=?",
                     (*fields.values(), db.now(), dataset_id))
        db.bump_revision(conn)
    return C.get_dataset(conn, dataset_id)


@app.post("/api/datasets/{dataset_id}/activate", dependencies=[Depends(require_admin)])
def dataset_activate(dataset_id: str, active: bool = True, conn=Depends(conn_dep)):
    d = conn.execute("SELECT status FROM dataset WHERE id = ?", (dataset_id,)).fetchone()
    if not d:
        _404("Dataset")
    if active and d[0] != "ready":
        raise HTTPException(409, f"Only processed datasets can be activated (status: {d[0]}).")
    conn.execute("UPDATE dataset SET active=?, updated_at=? WHERE id=?", (1 if active else 0, db.now(), dataset_id))
    db.bump_revision(conn)
    return C.get_dataset(conn, dataset_id)


@app.post("/api/datasets/{dataset_id}/versions/{version_id}/current", dependencies=[Depends(require_admin)])
def dataset_set_version(dataset_id: str, version_id: str, conn=Depends(conn_dep)):
    if not conn.execute("SELECT 1 FROM dataset_version WHERE id=? AND dataset_id=?", (version_id, dataset_id)).fetchone():
        _404("Dataset version")
    conn.execute("UPDATE dataset SET current_version_id=?, updated_at=? WHERE id=?", (version_id, db.now(), dataset_id))
    db.bump_revision(conn)
    return C.get_dataset(conn, dataset_id)


@app.delete("/api/datasets/{dataset_id}", dependencies=[Depends(require_admin)])
def dataset_delete(dataset_id: str, conn=Depends(conn_dep)):
    d = conn.execute("SELECT name FROM dataset WHERE id = ?", (dataset_id,)).fetchone()
    if not d:
        _404("Dataset")
    owned = conn.execute("SELECT COUNT(*) FROM earth_site WHERE source_dataset_id=?", (dataset_id,)).fetchone()[0] + \
        conn.execute("SELECT COUNT(*) FROM target_region WHERE source_dataset_id=?", (dataset_id,)).fetchone()[0]
    if owned:
        raise HTTPException(409, f"Dataset '{d[0]}' created {owned} site/target records. Deactivate it instead of deleting, "
                                 "so records referenced by other datasets are not orphaned.")
    paths = [r[0] for r in conn.execute("SELECT stored_path FROM dataset_version WHERE dataset_id=?", (dataset_id,))]
    paths += [r[0] for r in conn.execute("SELECT geojson_path FROM map_layer WHERE dataset_id=? AND geojson_path IS NOT NULL", (dataset_id,))]
    conn.execute("DELETE FROM dataset WHERE id=?", (dataset_id,))
    db.bump_revision(conn)
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            pass
    return {"deleted": dataset_id}


# ----------------------------------------------------------------------------- static
@app.exception_handler(500)
def _err(_, exc):  # pragma: no cover
    log.exception("Unhandled error")
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


_s = get_settings()
app.mount("/templates", StaticFiles(directory=_s.templates_dir), name="templates")
app.mount("/", StaticFiles(directory=_s.frontend_dir, html=True), name="frontend")
