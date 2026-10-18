import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ADMIN = "test-admin-token"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A fresh EarthTwin instance (own data dir, seeded through the real pipeline)."""
    monkeypatch.setenv("EARTHTWIN_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EARTHTWIN_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("EARTHTWIN_REMOTE_PROVIDERS", "0")
    from app.config import reset_settings
    reset_settings()
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        c.admin = {"X-Admin-Token": ADMIN}
        c.data_dir = tmp_path / "data"
        yield c
    reset_settings()


def do_import(client, path_or_bytes, filename, kind, mapping=None, metadata=None, expect_ok=True):
    """Upload → (optional) mapping → validate → process. Returns (session, job)."""
    data = Path(path_or_bytes).read_bytes() if isinstance(path_or_bytes, (str, Path)) else path_or_bytes
    r = client.post("/api/imports", files={"file": (filename, data)}, data={"kind": kind}, headers=client.admin)
    assert r.status_code == 200, r.text
    s = r.json()
    m = mapping if mapping is not None else s["proposed_mapping"]
    md = {**s["metadata"], **(metadata or {})}
    r = client.put(f"/api/imports/{s['id']}/mapping", json={"kind": kind, "mapping": m, "metadata": md}, headers=client.admin)
    assert r.status_code == 200, r.text
    s = r.json()
    if not expect_ok:
        return s, None
    assert s["status"] == "validated", s["validation"]["issues"]
    r = client.post(f"/api/imports/{s['id']}/process", headers=client.admin)
    assert r.status_code == 200, r.text
    job = r.json()
    import time
    for _ in range(100):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    return s, job
