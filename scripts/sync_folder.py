from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
        SELECT doc_id, file_path, content_hash, source_type, doc_state, tombstoned_at
        FROM documents
        WHERE {' AND '.join(clauses)}
    """
    with engine().begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    by_path: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_path.setdefault(str(r["file_path"]), []).append(dict(r))
    return by_path


def _batched(values: list[str], batch_size: int) -> list[list[str]]:
    size = max(1, int(batch_size))
    return [values[i:i + size] for i in range(0, len(values), size)]


def _delete_doc_ids(doc_ids: list[str]) -> None:
    if not doc_ids:
        return
    sql = "DELETE FROM documents WHERE doc_id = :doc_id"
    with engine().begin() as conn:
        for doc_id in doc_ids:
            conn.execute(text(sql), {"doc_id": doc_id})


def _mark_docs_active(doc_ids: list[str], batch_size: int) -> None:
    if not doc_ids:
        return
    sql = text(
        """
        UPDATE documents
        SET doc_state = 'active',
            state_reason = NULL,
            tombstoned_at = NULL,
            replaced_by_doc_id = NULL,
            updated_at = now(),
            doc_version = CASE WHEN doc_state = 'active' THEN doc_version ELSE doc_version + 1 END
        WHERE doc_id = ANY(:doc_ids)
        """
    )
    with engine().begin() as conn:
        for batch in _batched(doc_ids, batch_size):
            conn.execute(sql, {"doc_ids": batch})


def _mark_docs_tombstone_pending(doc_ids: list[str], reason: str, batch_size: int) -> None:
    if not doc_ids:
        return
    sql = text(
        """
        UPDATE documents
        SET doc_state = 'tombstone_pending',
            state_reason = :reason,
            tombstoned_at = COALESCE(tombstoned_at, now()),
            updated_at = now(),
            doc_version = CASE WHEN doc_state = 'tombstone_pending' THEN doc_version ELSE doc_version + 1 END
        WHERE doc_id = ANY(:doc_ids)
        """
    )
    with engine().begin() as conn:
        for batch in _batched(doc_ids, batch_size):
            conn.execute(sql, {"doc_ids": batch, "reason": reason})


def _mark_docs_tombstone(
    doc_ids: list[str],
    reason: str,
    batch_size: int,
    replaced_by_doc_id: str | None = None,
) -> None:
    if not doc_ids:
        return
    sql = text(
        """
        UPDATE documents
        SET doc_state = 'tombstone',
            state_reason = :reason,
            tombstoned_at = COALESCE(tombstoned_at, now()),
            replaced_by_doc_id = COALESCE(:replaced_by_doc_id, replaced_by_doc_id),
            updated_at = now(),
            doc_version = CASE WHEN doc_state = 'tombstone' THEN doc_version ELSE doc_version + 1 END
        WHERE doc_id = ANY(:doc_ids)
        """
    )
    with engine().begin() as conn:
        for batch in _batched(doc_ids, batch_size):
            conn.execute(
                sql,
                {
                    "doc_ids": batch,
                    "reason": reason,
                    "replaced_by_doc_id": replaced_by_doc_id,
                },
            )


def _as_utc_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except Exception:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def sync_path(
    path: str,
    source_type: str | None = None,
    author: str | None = None,
    year: int | None = None,
    ingest_root: str | None = None,
    delete_missing: bool = True,
    dry_run: bool = False,
    tombstone_mode: bool | None = None,
    tombstone_grace_seconds: int | None = None,
    anti_thrash_batch_size: int | None = None,
    now_utc: datetime | None = None,
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
    now = now_utc or datetime.now(timezone.utc)
    use_tombstone_mode = (
        bool(settings.sync_tombstone_enabled or settings.next_gen_rag_enabled)
        if tombstone_mode is None
        else bool(tombstone_mode)
    )
    grace_seconds = int(
        tombstone_grace_seconds
        if tombstone_grace_seconds is not None
        else settings.sync_tombstone_grace_seconds
    )
    batch_size = int(
        anti_thrash_batch_size
        if anti_thrash_batch_size is not None
        else settings.sync_anti_thrash_batch_size
    )

    created_docs = 0
    updated_docs = 0
    unchanged_docs = 0
    deleted_docs = 0
    tombstone_pending_docs = 0
    tombstoned_docs = 0
    reactivated_docs = 0
    errors: list[str] = []

    for file_path in files:
        abs_file = file_path.resolve(strict=False)
        key = str(abs_file)
        existing_rows = existing_by_path.get(key, [])
        existing_hashes = {str(r.get("content_hash")) for r in existing_rows}

        try:
            current_hash = _hash_file(abs_file)
            if current_hash in existing_hashes:
                if use_tombstone_mode:
                    matched_rows = [r for r in existing_rows if str(r.get("content_hash")) == current_hash]
                    to_reactivate = [
                        str(r["doc_id"])
                        for r in matched_rows
                        if str(r.get("doc_state") or "active") != "active"
                    ]
                    if to_reactivate:
                        if dry_run:
                            reactivated_docs += len(to_reactivate)
                        else:
                            _mark_docs_active(to_reactivate, batch_size=batch_size)
                            reactivated_docs += len(to_reactivate)
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
            if use_tombstone_mode:
                _mark_docs_tombstone(
                    stale_doc_ids,
                    reason="replaced_by_new_version",
                    batch_size=batch_size,
                    replaced_by_doc_id=new_doc_id,
                )
                tombstoned_docs += len(stale_doc_ids)
            else:
                _delete_doc_ids(stale_doc_ids)

            if existing_rows:
                updated_docs += 1
                if not use_tombstone_mode:
                    deleted_docs += len(stale_doc_ids)
            else:
                created_docs += 1
        except Exception as e:
            errors.append(f"{key}: {e}")

    if delete_missing:
        missing_doc_ids: list[str] = []
        missing_pending_doc_ids: list[str] = []
        missing_tombstone_doc_ids: list[str] = []

        for fp, rows in existing_by_path.items():
            if fp not in current_file_paths:
                if not use_tombstone_mode:
                    missing_doc_ids.extend([str(r["doc_id"]) for r in rows])
                    continue

                for row in rows:
                    doc_id = str(row["doc_id"])
                    state = str(row.get("doc_state") or "active")
                    if state == "tombstone":
                        continue
                    if state == "tombstone_pending":
                        tombstoned_at = _as_utc_datetime(row.get("tombstoned_at"))
                        elapsed = (now - tombstoned_at).total_seconds() if tombstoned_at else 0.0
                        if elapsed >= float(grace_seconds):
                            missing_tombstone_doc_ids.append(doc_id)
                    else:
                        missing_pending_doc_ids.append(doc_id)

        if dry_run and use_tombstone_mode:
            tombstone_pending_docs += len(missing_pending_doc_ids)
            tombstoned_docs += len(missing_tombstone_doc_ids)
        elif dry_run:
            deleted_docs += len(missing_doc_ids)
        elif use_tombstone_mode:
            _mark_docs_tombstone_pending(
                missing_pending_doc_ids,
                reason="missing_from_source",
                batch_size=batch_size,
            )
            _mark_docs_tombstone(
                missing_tombstone_doc_ids,
                reason="missing_from_source",
                batch_size=batch_size,
            )
            tombstone_pending_docs += len(missing_pending_doc_ids)
            tombstoned_docs += len(missing_tombstone_doc_ids)
        else:
            _delete_doc_ids(missing_doc_ids)
            deleted_docs += len(missing_doc_ids)

    return {
        "path": str(abs_path),
        "source_type": source_type,
        "dry_run": bool(dry_run),
        "delete_missing": bool(delete_missing),
        "tombstone_mode": bool(use_tombstone_mode),
        "tombstone_grace_seconds": grace_seconds,
        "anti_thrash_batch_size": batch_size,
        "scanned_files": len(files),
        "created_docs": created_docs,
        "updated_docs": updated_docs,
        "unchanged_docs": unchanged_docs,
        "deleted_docs": deleted_docs,
        "tombstone_pending_docs": tombstone_pending_docs,
        "tombstoned_docs": tombstoned_docs,
        "reactivated_docs": reactivated_docs,
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
    ap.add_argument("--tombstone-grace-seconds", type=int, default=None)
    ap.add_argument("--anti-thrash-batch-size", type=int, default=None)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--tombstone-mode", dest="tombstone_mode", action="store_true")
    group.add_argument("--no-tombstone-mode", dest="tombstone_mode", action="store_false")
    ap.set_defaults(tombstone_mode=None)
    args = ap.parse_args()

    summary = sync_path(
        path=args.path,
        source_type=args.source_type,
        author=args.author,
        year=args.year,
        ingest_root=args.ingest_root,
        dry_run=args.dry_run,
        delete_missing=not args.no_delete_missing,
        tombstone_mode=args.tombstone_mode,
        tombstone_grace_seconds=args.tombstone_grace_seconds,
        anti_thrash_batch_size=args.anti_thrash_batch_size,
    )
    print(summary)


if __name__ == "__main__":
    main()
