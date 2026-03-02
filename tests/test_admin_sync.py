import pytest
from fastapi import HTTPException

from app.api import routes_admin
from app.api.routes_admin import SyncRequest


def test_admin_sync_calls_sync_folder(monkeypatch):
    captured = {}

    monkeypatch.setattr(routes_admin, "_validated_ingest_path", lambda p: f"/validated/{p}")

    def _fake_sync_folder(**kwargs):
        captured.update(kwargs)
        return {
            "errors": [],
            "scanned_files": 1,
            "created_docs": 1,
            "updated_docs": 0,
            "unchanged_docs": 0,
            "deleted_docs": 0,
        }

    monkeypatch.setattr(routes_admin, "sync_folder", _fake_sync_folder)

    resp = routes_admin.admin_sync(
        SyncRequest(
            path="cell_haven_docs",
            source_type="haven_docs",
            delete_missing=True,
            dry_run=False,
        )
    )

    assert captured["path"] == "/validated/cell_haven_docs"
    assert captured["source_type"] == "haven_docs"
    assert resp["ok"] is True
    assert resp["summary"]["created_docs"] == 1


def test_admin_sync_returns_not_ok_when_errors(monkeypatch):
    monkeypatch.setattr(routes_admin, "_validated_ingest_path", lambda p: p)
    monkeypatch.setattr(
        routes_admin,
        "sync_folder",
        lambda **kwargs: {"errors": ["x"], "scanned_files": 0, "created_docs": 0, "updated_docs": 0, "unchanged_docs": 0, "deleted_docs": 0},
    )

    resp = routes_admin.admin_sync(SyncRequest(path="x", delete_missing=False))
    assert resp["ok"] is False


def test_admin_sync_requires_source_type_when_delete_missing_true():
    with pytest.raises(HTTPException) as exc:
        routes_admin.admin_sync(SyncRequest(path="x", delete_missing=True, source_type=None))
    assert exc.value.status_code == 400


def test_admin_sync_passes_tombstone_options(monkeypatch):
    captured = {}

    monkeypatch.setattr(routes_admin, "_validated_ingest_path", lambda p: p)

    def _fake_sync_folder(**kwargs):
        captured.update(kwargs)
        return {"errors": [], "scanned_files": 0, "created_docs": 0, "updated_docs": 0, "unchanged_docs": 0, "deleted_docs": 0}

    monkeypatch.setattr(routes_admin, "sync_folder", _fake_sync_folder)
    routes_admin.admin_sync(
        SyncRequest(
            path="x",
            source_type="haven_docs",
            delete_missing=True,
            tombstone_mode=True,
            tombstone_grace_seconds=120,
            anti_thrash_batch_size=50,
        )
    )

    assert captured["tombstone_mode"] is True
    assert captured["tombstone_grace_seconds"] == 120
    assert captured["anti_thrash_batch_size"] == 50
