from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.rag.ingest.cleaner import clean_text
from app.rag.ingest.loaders import load_any
from app.rag.index.db import engine
from app.rag.index.indexer import ingest_file
from app.rag.ingest.metadata import compute_hash
from app.settings import settings

SUPPORTED_EXTENSIONS = ["*.md", "*.markdown", "*.txt", "*.html", "*.htm", "*.pdf", "*.docx"]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _collect_files(path: Path, skip_roots: list[Path]) -> list[Path]:
    if not path.is_dir():
        return [path]

    files: list[Path] = []
    for ext in SUPPORTED_EXTENSIONS:
        files.extend(path.rglob(ext))
    unique_files = sorted(set(files))
    return [f for f in unique_files if not any(_is_within(f, root) for root in skip_roots)]


def _hash_file(path: Path) -> str:
    raw = load_any(path)
    txt = clean_text(raw)
    return compute_hash(txt)


def _fetch_existing_docs(scope_path: Path, source_type: str | None) -> dict[str, list[dict[str, Any]]]:
    clauses = ["file_path IS NOT NULL"]
    params: dict[str, Any] = {}
    if scope_path.is_file():
        clauses.append("file_path = :file_path")
        params["file_path"] = str(scope_path)
    else:
        clauses.append("(file_path = :root OR file_path LIKE :root_like)")
        params["root"] = str(scope_path)
        params["root_like"] = f"{scope_path}/%"
    if source_type is not None:
        clauses.append("source_type = :source_type")
        params["source_type"] = source_type

    sql = f"""
        SELECT doc_id, file_path, content_hash, source_type
        FROM documents
        WHERE {' AND '.join(clauses)}
    """
    with engine().begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    by_path: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_path.setdefault(str(r["file_path"]), []).append(dict(r))
    return by_path


def _delete_doc_ids(doc_ids: list[str]) -> None:
    if not doc_ids:
        return
    sql = "DELETE FROM documents WHERE doc_id = :doc_id"
    with engine().begin() as conn:
        for doc_id in doc_ids:
            conn.execute(text(sql), {"doc_id": doc_id})


def sync_path(
    path: str,
    source_type: str | None = None,
    author: str | None = None,
    year: int | None = None,
    ingest_root: str | None = None,
    delete_missing: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    if delete_missing and source_type is None:
        raise SystemExit("source_type must be set when delete_missing=true")

    p = Path(path).expanduser()
    if not p.exists():
        raise SystemExit(f"Path not found: {p}")

    configured_root = ingest_root or settings.ingest_root
    ingest_root_path = Path(configured_root).expanduser().resolve(strict=False) if configured_root else None
    abs_path = p.resolve(strict=False)
    if ingest_root_path is not None and not _is_within(abs_path, ingest_root_path):
        raise SystemExit(f"path must be under ingest root: {ingest_root_path}")

    root_dir = abs_path if abs_path.is_dir() else abs_path.parent
    skip_roots = [root_dir / "done", root_dir / "failed"]
    files = _collect_files(abs_path, skip_roots)

    scope = abs_path
    existing_by_path = _fetch_existing_docs(scope, source_type=source_type)
    current_file_paths = {str(f.resolve(strict=False)) for f in files}

    created_docs = 0
    updated_docs = 0
    unchanged_docs = 0
    deleted_docs = 0
    errors: list[str] = []

    for file_path in files:
        abs_file = file_path.resolve(strict=False)
        key = str(abs_file)
        existing_rows = existing_by_path.get(key, [])
        existing_hashes = {str(r.get("content_hash")) for r in existing_rows}

        try:
            current_hash = _hash_file(abs_file)
            if current_hash in existing_hashes:
                unchanged_docs += 1
                continue

            if dry_run:
                if existing_rows:
                    updated_docs += 1
                else:
                    created_docs += 1
                continue

            new_doc_id = ingest_file(abs_file, source_type=source_type, author=author, year=year)
            stale_doc_ids = [str(r["doc_id"]) for r in existing_rows if str(r["doc_id"]) != new_doc_id]
            _delete_doc_ids(stale_doc_ids)

            if existing_rows:
                updated_docs += 1
                deleted_docs += len(stale_doc_ids)
            else:
                created_docs += 1
        except Exception as e:
            errors.append(f"{key}: {e}")

    if delete_missing:
        missing_doc_ids: list[str] = []
        for fp, rows in existing_by_path.items():
            if fp not in current_file_paths:
                missing_doc_ids.extend([str(r["doc_id"]) for r in rows])
        if dry_run:
            deleted_docs += len(missing_doc_ids)
        else:
            _delete_doc_ids(missing_doc_ids)
            deleted_docs += len(missing_doc_ids)

    return {
        "path": str(abs_path),
        "source_type": source_type,
        "dry_run": bool(dry_run),
        "delete_missing": bool(delete_missing),
        "scanned_files": len(files),
        "created_docs": created_docs,
        "updated_docs": updated_docs,
        "unchanged_docs": unchanged_docs,
        "deleted_docs": deleted_docs,
        "errors": errors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--source-type", default=None)
    ap.add_argument("--author", default=None)
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--ingest-root", default=None)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--no-delete-missing", action="store_true", default=False)
    args = ap.parse_args()

    summary = sync_path(
        path=args.path,
        source_type=args.source_type,
        author=args.author,
        year=args.year,
        ingest_root=args.ingest_root,
        dry_run=args.dry_run,
        delete_missing=not args.no_delete_missing,
    )
    print(summary)


if __name__ == "__main__":
    main()
