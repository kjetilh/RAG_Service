from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from scripts import sync_folder as sync_mod


def test_collect_files_skips_done_and_failed(tmp_path: Path):
    root = tmp_path / "docs"
    (root / "done").mkdir(parents=True)
    (root / "failed").mkdir(parents=True)
    (root / "a.md").write_text("a", encoding="utf-8")
    (root / "done" / "b.md").write_text("b", encoding="utf-8")
    (root / "failed" / "c.md").write_text("c", encoding="utf-8")

    files = sync_mod._collect_files(root, [root / "done", root / "failed"])
    names = sorted([f.name for f in files])
    assert names == ["a.md"]


def test_sync_path_dry_run_counts_create_update_delete(monkeypatch, tmp_path: Path):
    root = tmp_path / "live_docs"
    root.mkdir(parents=True)
    (root / "new.md").write_text("new", encoding="utf-8")
    (root / "changed.md").write_text("changed", encoding="utf-8")

    existing = {
        str((root / "changed.md").resolve(strict=False)): [
            {"doc_id": "old-changed", "file_path": str(root / "changed.md"), "content_hash": "oldhash"},
        ],
        str((root / "deleted.md").resolve(strict=False)): [
            {"doc_id": "old-deleted", "file_path": str(root / "deleted.md"), "content_hash": "x"},
        ],
    }

    monkeypatch.setattr(sync_mod, "_fetch_existing_docs", lambda root_dir, source_type: existing)
    monkeypatch.setattr(sync_mod, "_hash_file", lambda p: f"hash-{p.name}")
    monkeypatch.setattr(sync_mod, "_delete_doc_ids", lambda doc_ids: None)
    monkeypatch.setattr(sync_mod, "ingest_file", lambda *args, **kwargs: "unused")

    summary = sync_mod.sync_path(
        path=str(root),
        source_type="docs",
        ingest_root=str(tmp_path),
        dry_run=True,
        delete_missing=True,
    )

    assert summary["created_docs"] == 1
    assert summary["updated_docs"] == 1
    assert summary["deleted_docs"] == 1
    assert summary["unchanged_docs"] == 0
    assert summary["errors"] == []


def test_sync_path_unchanged_when_hash_matches(monkeypatch, tmp_path: Path):
    root = tmp_path / "live_docs"
    root.mkdir(parents=True)
    file_path = root / "same.md"
    file_path.write_text("same", encoding="utf-8")

    existing = {
        str(file_path.resolve(strict=False)): [
            {"doc_id": "same-doc", "file_path": str(file_path), "content_hash": "samehash"},
        ]
    }

    monkeypatch.setattr(sync_mod, "_fetch_existing_docs", lambda root_dir, source_type: existing)
    monkeypatch.setattr(sync_mod, "_hash_file", lambda p: "samehash")
    monkeypatch.setattr(sync_mod, "_delete_doc_ids", lambda doc_ids: None)
    monkeypatch.setattr(sync_mod, "ingest_file", lambda *args, **kwargs: "unexpected")

    summary = sync_mod.sync_path(
        path=str(root),
        source_type="docs",
        ingest_root=str(tmp_path),
        dry_run=False,
        delete_missing=True,
    )

    assert summary["created_docs"] == 0
    assert summary["updated_docs"] == 0
    assert summary["unchanged_docs"] == 1
    assert summary["errors"] == []


def test_sync_path_requires_source_type_when_delete_missing_true(tmp_path: Path):
    root = tmp_path / "live_docs"
    root.mkdir(parents=True)

    with pytest.raises(SystemExit):
        sync_mod.sync_path(path=str(root), source_type=None, ingest_root=str(tmp_path), delete_missing=True)


def test_sync_path_tombstone_mode_marks_missing_pending(monkeypatch, tmp_path: Path):
    root = tmp_path / "live_docs"
    root.mkdir(parents=True)
    missing_fp = str((root / "missing.md").resolve(strict=False))

    existing = {
        missing_fp: [
            {"doc_id": "d1", "file_path": missing_fp, "content_hash": "h1", "doc_state": "active", "tombstoned_at": None}
        ]
    }
    pending_calls = []
    tomb_calls = []

    monkeypatch.setattr(sync_mod, "_fetch_existing_docs", lambda root_dir, source_type: existing)
    monkeypatch.setattr(sync_mod, "_mark_docs_tombstone_pending", lambda doc_ids, reason, batch_size: pending_calls.append((doc_ids, reason, batch_size)))
    monkeypatch.setattr(sync_mod, "_mark_docs_tombstone", lambda doc_ids, reason, batch_size, replaced_by_doc_id=None: tomb_calls.append((doc_ids, reason, batch_size, replaced_by_doc_id)))
    monkeypatch.setattr(sync_mod, "_delete_doc_ids", lambda doc_ids: (_ for _ in ()).throw(AssertionError("delete should not run")))

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    summary = sync_mod.sync_path(
        path=str(root),
        source_type="docs",
        ingest_root=str(tmp_path),
        delete_missing=True,
        dry_run=False,
        tombstone_mode=True,
        tombstone_grace_seconds=900,
        anti_thrash_batch_size=25,
        now_utc=now,
    )

    assert summary["deleted_docs"] == 0
    assert summary["tombstone_pending_docs"] == 1
    assert summary["tombstoned_docs"] == 0
    assert pending_calls[0][0] == ["d1"]
    assert tomb_calls[0][0] == []


def test_sync_path_tombstone_mode_promotes_pending_after_grace(monkeypatch, tmp_path: Path):
    root = tmp_path / "live_docs"
    root.mkdir(parents=True)
    missing_fp = str((root / "missing.md").resolve(strict=False))
    old_ts = datetime(2025, 12, 1, tzinfo=timezone.utc)

    existing = {
        missing_fp: [
            {
                "doc_id": "d2",
                "file_path": missing_fp,
                "content_hash": "h2",
                "doc_state": "tombstone_pending",
                "tombstoned_at": old_ts,
            }
        ]
    }
    pending_calls = []
    tomb_calls = []

    monkeypatch.setattr(sync_mod, "_fetch_existing_docs", lambda root_dir, source_type: existing)
    monkeypatch.setattr(sync_mod, "_mark_docs_tombstone_pending", lambda doc_ids, reason, batch_size: pending_calls.append(doc_ids))
    monkeypatch.setattr(sync_mod, "_mark_docs_tombstone", lambda doc_ids, reason, batch_size, replaced_by_doc_id=None: tomb_calls.append(doc_ids))

    summary = sync_mod.sync_path(
        path=str(root),
        source_type="docs",
        ingest_root=str(tmp_path),
        delete_missing=True,
        dry_run=False,
        tombstone_mode=True,
        tombstone_grace_seconds=300,
        anti_thrash_batch_size=20,
        now_utc=old_ts + timedelta(hours=2),
    )

    assert summary["tombstone_pending_docs"] == 0
    assert summary["tombstoned_docs"] == 1
    assert pending_calls[0] == []
    assert tomb_calls[0] == ["d2"]


def test_sync_path_tombstone_mode_reactivates_same_hash(monkeypatch, tmp_path: Path):
    root = tmp_path / "live_docs"
    root.mkdir(parents=True)
    file_path = root / "doc.md"
    file_path.write_text("same", encoding="utf-8")

    key = str(file_path.resolve(strict=False))
    existing = {
        key: [
            {
                "doc_id": "d3",
                "file_path": key,
                "content_hash": "samehash",
                "doc_state": "tombstone_pending",
                "tombstoned_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ]
    }
    reactivated = []

    monkeypatch.setattr(sync_mod, "_fetch_existing_docs", lambda root_dir, source_type: existing)
    monkeypatch.setattr(sync_mod, "_hash_file", lambda p: "samehash")
    monkeypatch.setattr(sync_mod, "_mark_docs_active", lambda doc_ids, batch_size: reactivated.extend(doc_ids))
    monkeypatch.setattr(sync_mod, "_mark_docs_tombstone_pending", lambda doc_ids, reason, batch_size: None)
    monkeypatch.setattr(sync_mod, "_mark_docs_tombstone", lambda doc_ids, reason, batch_size, replaced_by_doc_id=None: None)

    summary = sync_mod.sync_path(
        path=str(root),
        source_type="docs",
        ingest_root=str(tmp_path),
        delete_missing=True,
        dry_run=False,
        tombstone_mode=True,
    )

    assert summary["unchanged_docs"] == 1
    assert summary["reactivated_docs"] == 1
    assert reactivated == ["d3"]


def test_sync_path_tombstone_mode_marks_replaced_docs(monkeypatch, tmp_path: Path):
    root = tmp_path / "live_docs"
    root.mkdir(parents=True)
    file_path = root / "doc.md"
    file_path.write_text("new", encoding="utf-8")
    key = str(file_path.resolve(strict=False))

    existing = {
        key: [
            {"doc_id": "old-doc", "file_path": key, "content_hash": "oldhash", "doc_state": "active", "tombstoned_at": None}
        ]
    }
    tombstoned = []

    monkeypatch.setattr(sync_mod, "_fetch_existing_docs", lambda root_dir, source_type: existing)
    monkeypatch.setattr(sync_mod, "_hash_file", lambda p: "newhash")
    monkeypatch.setattr(sync_mod, "ingest_file", lambda *args, **kwargs: "new-doc")
    monkeypatch.setattr(
        sync_mod,
        "_mark_docs_tombstone",
        lambda doc_ids, reason, batch_size, replaced_by_doc_id=None: tombstoned.append((doc_ids, reason, replaced_by_doc_id)),
    )
    monkeypatch.setattr(sync_mod, "_delete_doc_ids", lambda doc_ids: (_ for _ in ()).throw(AssertionError("delete should not run")))
    monkeypatch.setattr(sync_mod, "_mark_docs_tombstone_pending", lambda doc_ids, reason, batch_size: None)

    summary = sync_mod.sync_path(
        path=str(root),
        source_type="docs",
        ingest_root=str(tmp_path),
        delete_missing=True,
        dry_run=False,
        tombstone_mode=True,
    )

    assert summary["updated_docs"] == 1
    assert summary["deleted_docs"] == 0
    assert summary["tombstoned_docs"] == 1
    assert tombstoned[0][0] == ["old-doc"]
    assert tombstoned[0][1] == "replaced_by_new_version"
    assert tombstoned[0][2] == "new-doc"
