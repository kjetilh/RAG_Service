from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy import text

from app.rag.index.db import engine
from app.rag.index.embedder import default_embedder
from app.rag.index.indexer import upsert_chunk, upsert_document
from app.rag.index.vector_store import upsert_embedding
from app.rag.ingest.metadata import compute_hash

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_TYPE = "cellprotocol_docs"


def _stable_doc_id(repo: str, target_endpoint: str) -> str:
    digest = hashlib.sha256(f"{repo}|{target_endpoint}".encode("utf-8")).hexdigest()
    return f"cell-contract-{digest[:16]}"


def _stable_chunk_id(doc_id: str, raw_id: str) -> str:
    digest = hashlib.sha256(f"{doc_id}|{raw_id}".encode("utf-8")).hexdigest()
    return f"{doc_id}-chunk-{digest[:16]}"


def _section_path(chunk: dict[str, Any]) -> str:
    parts = [str(chunk.get("documentKind") or "chunk")]
    key = str(chunk.get("key") or "").strip()
    phase = str(chunk.get("phase") or "").strip()
    if key:
        parts.append(key)
    if phase:
        parts.append(phase)
    return "/".join(parts)


def _normalize_chunks(record: dict[str, Any]) -> list[dict[str, Any]]:
    raw_chunks = list(record.get("chunks") or [])
    normalized: list[dict[str, Any]] = []

    for ordinal, chunk in enumerate(raw_chunks, start=1):
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        normalized.append(
            {
                "raw_id": str(chunk.get("id") or f"chunk-{ordinal}"),
                "section_path": _section_path(chunk),
                "ordinal": ordinal,
                "content": content,
            }
        )

    if normalized:
        return normalized

    markdown = str(record.get("recordMarkdown") or record.get("markdown") or "").strip()
    if markdown:
        return [
            {
                "raw_id": "summary-markdown",
                "section_path": "summary",
                "ordinal": 1,
                "content": markdown,
            }
        ]

    raise ValueError("Contract verification ingest requires at least one non-empty chunk or recordMarkdown.")


def _replace_chunks(doc_id: str, normalized_chunks: list[dict[str, Any]]) -> None:
    with engine().begin() as conn:
        conn.execute(text("DELETE FROM chunks WHERE doc_id = :doc_id"), {"doc_id": doc_id})

    for chunk in normalized_chunks:
        upsert_chunk(
            chunk_id=_stable_chunk_id(doc_id, chunk["raw_id"]),
            doc_id=doc_id,
            section_path=chunk["section_path"],
            ordinal=chunk["ordinal"],
            content=chunk["content"],
        )

    embedder = default_embedder()
    vectors = embedder.embed([chunk["content"] for chunk in normalized_chunks])
    for chunk, vector in zip(normalized_chunks, vectors):
        upsert_embedding(_stable_chunk_id(doc_id, chunk["raw_id"]), vector)


def _touch_document_state(doc_id: str) -> None:
    sql = text(
        """
        UPDATE documents
        SET doc_state = 'active',
            state_reason = NULL,
            tombstoned_at = NULL,
            replaced_by_doc_id = NULL,
            updated_at = now()
        WHERE doc_id = :doc_id
        """
    )
    with engine().begin() as conn:
        conn.execute(sql, {"doc_id": doc_id})


def upsert_contract_verification_record(case_id: str, record: dict[str, Any]) -> dict[str, Any]:
    repo = str(record.get("repo") or "CellProtocol").strip() or "CellProtocol"
    cell_type = str(record.get("cellType") or "UnknownCell").strip() or "UnknownCell"
    target_endpoint = str(record.get("targetEndpoint") or "").strip()
    if not target_endpoint:
        raise ValueError("targetEndpoint is required.")

    source_type = str(record.get("sourceType") or DEFAULT_SOURCE_TYPE).strip() or DEFAULT_SOURCE_TYPE
    verification_status = str(record.get("verificationStatus") or "unknown").strip() or "unknown"
    last_verified_at = str(record.get("lastVerifiedAt") or "").strip() or None
    contract_version = record.get("contractVersion")
    failed_assertion_count = int(record.get("failedAssertionCount") or 0)
    target_label = str(record.get("targetLabel") or "").strip() or None

    normalized_chunks = _normalize_chunks(record)
    doc_id = _stable_doc_id(repo, target_endpoint)
    title = f"{cell_type} verification for {target_endpoint}"
    content_hash = compute_hash("\n\n".join(chunk["content"] for chunk in normalized_chunks))

    identifiers_json = json.dumps(
        {
            "record_type": "cell_contract_verification",
            "case_id": case_id,
            "repo": repo,
            "cell_type": cell_type,
            "target_endpoint": target_endpoint,
            "target_label": target_label,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    meta_sources_json = json.dumps(
        {
            "verification_status": verification_status,
            "last_verified_at": last_verified_at,
            "contract_version": contract_version,
            "failed_assertion_count": failed_assertion_count,
            "chunk_count": len(normalized_chunks),
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    upsert_document(
        doc_id=doc_id,
        title=title,
        author=repo,
        year=None,
        source_type=source_type,
        content_hash=content_hash,
        publisher=repo,
        url=None,
        language="en",
        identifiers_json=identifiers_json,
        meta_sources_json=meta_sources_json,
        file_path=None,
    )
    _touch_document_state(doc_id)
    _replace_chunks(doc_id, normalized_chunks)

    logger.info(
        "Upserted contract verification record",
        extra={
            "doc_id": doc_id,
            "case_id": case_id,
            "repo": repo,
            "target_endpoint": target_endpoint,
            "chunk_count": len(normalized_chunks),
            "verification_status": verification_status,
        },
    )

    return {
        "doc_id": doc_id,
        "title": title,
        "source_type": source_type,
        "chunk_count": len(normalized_chunks),
    }
