from pathlib import Path

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
