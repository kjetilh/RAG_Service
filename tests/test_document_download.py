from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes_chat import _resolve_download_path
from app.settings import settings


@pytest.fixture(autouse=True)
def restore_ingest_root():
    original = settings.ingest_root
    yield
    settings.ingest_root = original


def test_resolve_download_path_direct_file(tmp_path: Path):
    settings.ingest_root = str(tmp_path)
    p = tmp_path / "docs" / "example.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("hello", encoding="utf-8")

    resolved = _resolve_download_path(str(p))
    assert resolved == p


def test_resolve_download_path_done_fallback(tmp_path: Path):
    settings.ingest_root = str(tmp_path)
    stored = tmp_path / "docs" / "moved.md"
    done = tmp_path / "done" / "docs" / "moved.md"
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text("# moved", encoding="utf-8")

    resolved = _resolve_download_path(str(stored))
    assert resolved == done


def test_resolve_download_path_rejects_outside_ingest_root(tmp_path: Path):
    settings.ingest_root = str(tmp_path / "uploads")
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        _resolve_download_path(str(outside))
    assert exc.value.status_code == 404
