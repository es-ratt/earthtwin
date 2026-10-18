"""Start EarthTwin locally:  python run.py  [--host 0.0.0.0] [--port 8000]

Loads `.env` if present. If EARTHTWIN_ADMIN_TOKEN is not set, a random token is
generated once, stored in data/admin_token.txt (owner-readable only) and printed,
so Data Center changes are always protected.
"""
import argparse
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))


def load_env():
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def ensure_token():
    if os.environ.get("EARTHTWIN_ADMIN_TOKEN"):
        return None
    data = Path(os.environ.get("EARTHTWIN_DATA_DIR", ROOT / "data"))
    data.mkdir(parents=True, exist_ok=True)
    tf = data / "admin_token.txt"
    if not tf.exists():
        tf.write_text(secrets.token_urlsafe(24))
        tf.chmod(0o600)
    os.environ["EARTHTWIN_ADMIN_TOKEN"] = tf.read_text().strip()
    return tf


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--reload", action="store_true")
    a = ap.parse_args()
    load_env()
    tf = ensure_token()
    import uvicorn
    print(f"\n  EarthTwin → http://{a.host}:{a.port}/   (API docs: /api/docs)", flush=True)
    if tf:
        print(f"  Data Center admin token (from {tf}): {os.environ['EARTHTWIN_ADMIN_TOKEN']}\n", flush=True)
    uvicorn.run("app.main:app", host=a.host, port=a.port, reload=a.reload, app_dir=str(ROOT / "backend"))
