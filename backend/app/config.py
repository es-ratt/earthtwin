"""Environment-based configuration.

Every setting can be overridden with an environment variable (or a `.env` file
in the repository root, loaded by `run.py`). Nothing secret is ever sent to the
browser.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("EARTHTWIN_DATA_DIR", str(REPO_ROOT / "data"))))
    admin_token: str = field(default_factory=lambda: _env("EARTHTWIN_ADMIN_TOKEN", ""))
    # Upload limits (bytes). Rasters are processed server-side with windowed reads,
    # so they may be larger than tabular files.
    max_table_bytes: int = field(default_factory=lambda: int(_env("EARTHTWIN_MAX_TABLE_MB", "50")) * 1024 * 1024)
    max_raster_bytes: int = field(default_factory=lambda: int(_env("EARTHTWIN_MAX_RASTER_MB", "2048")) * 1024 * 1024)
    # Similarity engine thresholds (documented in docs/METHODOLOGY.md)
    min_weight_coverage: float = field(default_factory=lambda: float(_env("EARTHTWIN_MIN_COVERAGE", "0.6")))
    min_criteria: int = field(default_factory=lambda: int(_env("EARTHTWIN_MIN_CRITERIA", "3")))
    seed_demo: bool = field(default_factory=lambda: _env("EARTHTWIN_SEED_DEMO", "1") == "1")
    enable_remote_providers: bool = field(default_factory=lambda: _env("EARTHTWIN_REMOTE_PROVIDERS", "1") == "1")
    frontend_dir: Path = REPO_ROOT / "frontend"
    templates_dir: Path = REPO_ROOT / "templates"
    docs_dir: Path = REPO_ROOT / "docs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "earthtwin.sqlite3"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def layer_dir(self) -> Path:
        return self.data_dir / "layers"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.upload_dir, self.export_dir, self.layer_dir):
            d.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Used by tests to pick up changed environment variables."""
    global _settings
    _settings = None
