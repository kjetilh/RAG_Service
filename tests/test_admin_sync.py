import pytest
from fastapi import HTTPException

from app.api import routes_admin
from app.api.routes_admin import CatalogPublishRequest, CatalogSourceRequest, MediaPublishRequest, SyncRequest


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


def test_admin_catalog_publish_delegates(monkeypatch):
    captured = {}

    def _fake_publish_catalog(payload):
        captured.update(payload)
        return {"ok": True, "upserted": len(payload["chunks"])}

    monkeypatch.setattr(routes_admin, "publish_catalog", _fake_publish_catalog)

    resp = routes_admin.admin_catalog_publish(
        CatalogPublishRequest(
            case_id="dimy_docs",
            source_repo="CellScaffold",
            source_type="cellprotocol_docs",
            chunks=[{"chunk_id": "c1", "title": "T", "content": "Body"}],
        )
    )

    assert resp == {"ok": True, "upserted": 1}
    assert captured["case_id"] == "dimy_docs"
    assert captured["chunks"][0]["chunk_id"] == "c1"


def test_admin_catalog_reindex_delegates(monkeypatch):
    captured = {}

    def _fake_reindex_catalog(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "reindexed_chunks": 2}

    monkeypatch.setattr(routes_admin, "reindex_catalog", _fake_reindex_catalog)

    resp = routes_admin.admin_catalog_reindex(
        CatalogSourceRequest(case_id="dimy_docs", source_repo="CellScaffold", source_type="cellprotocol_docs")
    )

    assert resp["reindexed_chunks"] == 2
    assert captured == {
        "case_id": "dimy_docs",
        "source_repo": "CellScaffold",
        "source_type": "cellprotocol_docs",
    }


def test_admin_media_publish_delegates(monkeypatch):
    captured = {}

    def _fake_publish_media(payload):
        captured.update(payload)
        return {"ok": True, "doc_id": "media-1"}

    monkeypatch.setattr(routes_admin, "publish_media", _fake_publish_media)

    resp = routes_admin.admin_media_publish(
        MediaPublishRequest(
            case_id="dimy_docs",
            source_repo="CellScaffold",
            source_type="cellprotocol_docs",
            media={"id": "m1", "title": "Screenshot", "text": "Alt text"},
        )
    )

    assert resp == {"ok": True, "doc_id": "media-1"}
    assert captured["media"]["id"] == "m1"
