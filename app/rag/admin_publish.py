from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from sqlalchemy import text

from app.rag.index.db import engine
from app.rag.index.embedder import default_embedder
from app.rag.index.indexer import upsert_chunk, upsert_document
from app.rag.index.vector_store import upsert_embedding
from app.rag.ingest.metadata import compute_hash


CATALOG_RECORD_TYPE = "rag_catalog_chunk"
MEDIA_RECORD_TYPE = "rag_media_asset"


def _stable_doc_id(record_type: str, case_id: str, source_repo: str, source_type: str, item_id: str) -> str:
    digest = hashlib.sha256(
        f"{record_type}|{case_id}|{source_repo}|{source_type}|{item_id}".encode("utf-8")
    ).hexdigest()
    prefix = "catalog" if record_type == CATALOG_RECORD_TYPE else "media"
    return f"{prefix}-{digest[:20]}"


def _stable_chunk_id(doc_id: str) -> str:
    return f"{doc_id}-chunk-0001"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _touch_active(doc_id: str) -> None:
    with engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE documents
                SET doc_state = 'active',
                    state_reason = NULL,
                    tombstoned_at = NULL,
                    replaced_by_doc_id = NULL,
                    updated_at = now()
                WHERE doc_id = :doc_id
                """
            ),
            {"doc_id": doc_id},
        )


def _replace_single_chunk(doc_id: str, content: str) -> None:
    chunk_id = _stable_chunk_id(doc_id)
    with engine().begin() as conn:
        conn.execute(text("DELETE FROM chunks WHERE doc_id = :doc_id"), {"doc_id": doc_id})
    upsert_chunk(chunk_id=chunk_id, doc_id=doc_id, section_path="content", ordinal=1, content=content)
    vector = default_embedder().embed([content])[0]
    upsert_embedding(chunk_id, vector)


def _upsert_searchable_doc(
    *,
    record_type: str,
    case_id: str,
    source_repo: str,
    source_commit: str | None,
    source_type: str,
    item_id: str,
    title: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    normalized_content = (content or "").strip()
    if not normalized_content:
        raise ValueError("content must be non-empty")

    doc_id = _stable_doc_id(record_type, case_id, source_repo, source_type, item_id)
    identifiers = {
        "record_type": record_type,
        "case_id": case_id,
        "source_repo": source_repo,
        "source_type": source_type,
        "item_id": item_id,
    }
    meta_sources = {
        "source_commit": source_commit,
        "metadata": metadata or {},
    }
    upsert_document(
        doc_id=doc_id,
        title=title.strip() or item_id,
        author=source_repo,
        year=None,
        source_type=source_type,
        content_hash=compute_hash(normalized_content),
        publisher=source_repo,
        url=None,
        language=None,
        identifiers_json=_json_dumps(identifiers),
        meta_sources_json=_json_dumps(meta_sources),
        file_path=None,
    )
    _touch_active(doc_id)
    _replace_single_chunk(doc_id, normalized_content)
    return doc_id


def _matching_docs(record_type: str, case_id: str, source_repo: str | None, source_type: str | None) -> list[str]:
    clauses = ["identifiers ->> 'record_type' = :record_type", "identifiers ->> 'case_id' = :case_id"]
    params: dict[str, Any] = {"record_type": record_type, "case_id": case_id}
    if source_repo:
        clauses.append("identifiers ->> 'source_repo' = :source_repo")
        params["source_repo"] = source_repo
    if source_type:
        clauses.append("source_type = :source_type")
        params["source_type"] = source_type
    sql = text(
        f"""
        SELECT doc_id
        FROM documents
        WHERE {' AND '.join(clauses)}
        ORDER BY doc_id
        """
    )
    with engine().begin() as conn:
        return [str(row[0]) for row in conn.execute(sql, params).fetchall()]


def _tombstone_docs(doc_ids: list[str], reason: str) -> int:
    if not doc_ids:
        return 0
    with engine().begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE documents
                SET doc_state = 'tombstone',
                    state_reason = :reason,
                    tombstoned_at = now(),
                    updated_at = now()
                WHERE doc_id = ANY(:doc_ids)
                """
            ),
            {"doc_ids": doc_ids, "reason": reason},
        )
        return int(result.rowcount or 0)


def publish_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    case_id = str(payload.get("case_id") or "").strip()
    source_repo = str(payload.get("source_repo") or "").strip()
    source_type = str(payload.get("source_type") or "").strip()
    source_commit = str(payload.get("source_commit") or "").strip() or None
    chunks = list(payload.get("chunks") or [])
    replace_source = bool(payload.get("replace_source", True))
    dry_run = bool(payload.get("dry_run", False))

    if not case_id:
        raise ValueError("case_id is required")
    if not source_repo:
        raise ValueError("source_repo is required")
    if not source_type:
        raise ValueError("source_type is required")

    incoming_ids = [
        str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
        for chunk in chunks
        if isinstance(chunk, dict)
    ]
    incoming_ids = [item_id for item_id in incoming_ids if item_id]
    incoming_doc_ids = {
        _stable_doc_id(CATALOG_RECORD_TYPE, case_id, source_repo, source_type, item_id)
        for item_id in incoming_ids
    }
    existing_doc_ids = set(_matching_docs(CATALOG_RECORD_TYPE, case_id, source_repo, source_type))
    would_tombstone = sorted(existing_doc_ids - incoming_doc_ids) if replace_source else []

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "would_upsert": len(incoming_ids),
            "would_tombstone": len(would_tombstone),
            "tombstone_doc_ids": would_tombstone,
        }

    upserted: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict):
            continue
        item_id = str(chunk.get("chunk_id") or chunk.get("id") or f"chunk-{idx}").strip()
        content = str(chunk.get("content") or chunk.get("body") or "").strip()
        if not content:
            continue
        title = str(chunk.get("title") or item_id).strip()
        metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
        upserted.append(
            _upsert_searchable_doc(
                record_type=CATALOG_RECORD_TYPE,
                case_id=case_id,
                source_repo=source_repo,
                source_commit=source_commit,
                source_type=source_type,
                item_id=item_id,
                title=title,
                content=content,
                metadata=metadata,
            )
        )

    tombstoned = _tombstone_docs(would_tombstone, "catalog_replace_source") if replace_source else 0
    return {
        "ok": True,
        "dry_run": False,
        "upserted": len(upserted),
        "tombstoned": tombstoned,
        "doc_ids": upserted,
    }


def _status(record_type: str, case_id: str, source_repo: str | None, source_type: str | None) -> dict[str, Any]:
    doc_ids = _matching_docs(record_type, case_id, source_repo, source_type)
    if not doc_ids:
        return {
            "ok": True,
            "case_id": case_id,
            "source_repo": source_repo,
            "source_type": source_type,
            "document_count": 0,
            "active_document_count": 0,
            "chunk_count": 0,
            "last_updated_at": None,
        }
    with engine().begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                  COUNT(DISTINCT d.doc_id) AS document_count,
                  COUNT(DISTINCT d.doc_id) FILTER (WHERE COALESCE(d.doc_state, 'active') = 'active') AS active_document_count,
                  COUNT(c.chunk_id) AS chunk_count,
                  MAX(d.updated_at) AS last_updated_at
                FROM documents d
                LEFT JOIN chunks c ON c.doc_id = d.doc_id
                WHERE d.doc_id = ANY(:doc_ids)
                """
            ),
            {"doc_ids": doc_ids},
        ).mappings().one()
    return {
        "ok": True,
        "case_id": case_id,
        "source_repo": source_repo,
        "source_type": source_type,
        "document_count": int(row["document_count"] or 0),
        "active_document_count": int(row["active_document_count"] or 0),
        "chunk_count": int(row["chunk_count"] or 0),
        "last_updated_at": row["last_updated_at"],
    }


def catalog_status(case_id: str, source_repo: str | None = None, source_type: str | None = None) -> dict[str, Any]:
    return _status(CATALOG_RECORD_TYPE, case_id, source_repo, source_type)


def media_status(case_id: str, source_repo: str | None = None, source_type: str | None = None) -> dict[str, Any]:
    return _status(MEDIA_RECORD_TYPE, case_id, source_repo, source_type)


def reindex_catalog(case_id: str, source_repo: str | None = None, source_type: str | None = None) -> dict[str, Any]:
    doc_ids = _matching_docs(CATALOG_RECORD_TYPE, case_id, source_repo, source_type)
    if not doc_ids:
        return {"ok": True, "reindexed_chunks": 0, "document_count": 0}
    with engine().begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT chunk_id, content
                FROM chunks
                WHERE doc_id = ANY(:doc_ids)
                ORDER BY doc_id, ordinal, chunk_id
                """
            ),
            {"doc_ids": doc_ids},
        ).fetchall()
    if not rows:
        return {"ok": True, "reindexed_chunks": 0, "document_count": len(doc_ids)}
    vectors = default_embedder().embed([str(row[1]) for row in rows])
    for row, vector in zip(rows, vectors):
        upsert_embedding(str(row[0]), vector)
    return {"ok": True, "reindexed_chunks": len(rows), "document_count": len(doc_ids)}


def _media_content(media: dict[str, Any], root_metadata: dict[str, Any]) -> str:
    title = str(media.get("title") or media.get("filename") or media.get("id") or "Media asset")
    mime_type = str(media.get("mime_type") or media.get("content_type") or "").strip()
    delivery = media.get("delivery") if isinstance(media.get("delivery"), dict) else {}
    content_text = str(media.get("text") or media.get("content") or "").strip()

    if not content_text and delivery.get("mode") == "inlineBase64":
        raw = str(delivery.get("bytes_base64") or "").strip()
        if raw:
            try:
                decoded = base64.b64decode(raw, validate=True)
                if mime_type.startswith("text/") or mime_type in {"application/json", "application/xml"}:
                    content_text = decoded.decode("utf-8", errors="replace").strip()
            except Exception:
                content_text = ""

    if content_text:
        return content_text

    summary = {
        "title": title,
        "mime_type": mime_type or None,
        "sha256": media.get("sha256"),
        "size_bytes": media.get("size_bytes"),
        "metadata": root_metadata,
    }
    return "Media asset metadata for RAG indexing:\n" + _json_dumps(summary)


def publish_media(payload: dict[str, Any]) -> dict[str, Any]:
    case_id = str(payload.get("case_id") or "").strip()
    source_type = str(payload.get("source_type") or "").strip()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    source_repo = str(payload.get("source_repo") or metadata.get("source_repo") or "").strip()
    media = payload.get("media") if isinstance(payload.get("media"), dict) else {}
    if not case_id:
        raise ValueError("case_id is required")
    if not source_type:
        raise ValueError("source_type is required")
    if not source_repo:
        raise ValueError("source_repo is required in payload or metadata")
    if not media:
        raise ValueError("media object is required")

    item_id = str(media.get("id") or media.get("sha256") or media.get("title") or "media").strip()
    title = str(media.get("title") or media.get("filename") or item_id).strip()
    content = _media_content(media, metadata)
    doc_id = _upsert_searchable_doc(
        record_type=MEDIA_RECORD_TYPE,
        case_id=case_id,
        source_repo=source_repo,
        source_commit=str(payload.get("source_commit") or "").strip() or None,
        source_type=source_type,
        item_id=item_id,
        title=title,
        content=content,
        metadata={**metadata, "media": {k: v for k, v in media.items() if k != "delivery"}},
    )
    return {"ok": True, "doc_id": doc_id, "title": title, "source_type": source_type}
