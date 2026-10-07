from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from app.models.schemas import Citation


@dataclass
class PackedContext:
    context_text: str
    citations: List[Citation]
    debug: Optional[Dict[str, Any]] = None


class CandidateList(list):
    """Retrieval candidates plus the query vector and filters they came from."""

    query_emb = None
    filters = None


def _select(candidates, top_k: int, max_chunks_per_doc: int) -> list:
    selected = []
    per_doc: Dict[str, int] = {}

    def _sort_key(x):
        return (
            -float(getattr(x, "score", 0.0)),
            str(getattr(x, "doc_id", "")),
            int(getattr(x, "ordinal", 0)),
            str(getattr(x, "chunk_id", "")),
        )

    for c in sorted(candidates, key=_sort_key):
        if len(selected) >= top_k:
            break
        doc_id = getattr(c, "doc_id", None)
        if not doc_id:
            continue
        n = per_doc.get(doc_id, 0)
        if n >= max_chunks_per_doc:
            continue
        per_doc[doc_id] = n + 1
        selected.append(c)
    return selected


def select_with_linked_documents(candidates, top_k: int, max_chunks_per_doc: int, query_emb=None, filters=None) -> list:
    """Selection with reserved slots for linked documents (GRAPH_MODE=expand).

    The usual selection decides which documents are on top. If documents linked
    from them are missing, their best chunk takes the last places; the places
    above are filled by the same ranking as before.
    """
    from app.settings import settings

    base = _select(candidates, top_k, max_chunks_per_doc)
    if str(getattr(settings, "graph_mode", "off")).lower() != "expand" or not base or query_emb is None:
        return base
    try:
        from app.rag.retrieve.graph_expand import linked_document_chunks
        from app.rag.retrieve.hybrid import _row_to_chunk

        doc_ids: list[str] = []
        for c in base:
            if c.doc_id not in doc_ids:
                doc_ids.append(c.doc_id)
        rows = linked_document_chunks(doc_ids, query_emb, filters)
    except Exception as exc:  # the graph is an addition; it must never fail a request
        print(f"[graph] expansion skipped: {exc!r}")
        return base
    if not rows:
        return base
    kept = _select(candidates, max(1, top_k - len(rows)), max_chunks_per_doc)
    floor = min(float(getattr(c, "score", 0.0)) for c in kept) if kept else 0.0
    extra = []
    for i, r in enumerate(rows):
        chunk = _row_to_chunk(r, "graph")
        chunk.score = floor - (i + 1) * 1e-6  # keeps them last under the deterministic sort
        extra.append(chunk)
    return kept + extra


def pack_context(candidates, top_k: int, max_chunks_per_doc: int = 4, query_emb=None, filters=None) -> PackedContext:
    # candidates: list[RetrievedChunk] (fra hybrid_retrieve / reranker)
    if query_emb is None:
        query_emb = getattr(candidates, "query_emb", None)
    if filters is None:
        filters = getattr(candidates, "filters", None)
    selected = select_with_linked_documents(candidates, top_k, max_chunks_per_doc, query_emb=query_emb, filters=filters)
    return _pack_selected(selected, top_k, max_chunks_per_doc)


def _pack_selected(selected, top_k: int, max_chunks_per_doc: int) -> PackedContext:
    per_doc: Dict[str, int] = {}
    for c in selected:
        per_doc[getattr(c, "doc_id", "")] = per_doc.get(getattr(c, "doc_id", ""), 0) + 1

    # Bygg context + citations
    parts: List[str] = []
    citations: List[Citation] = []

    for c in selected:
        chunk_id = getattr(c, "chunk_id", "")
        doc_id = getattr(c, "doc_id", "")
        content = getattr(c, "content", "") or ""
        section_path = getattr(c, "section_path", None)
        title = getattr(c, "title", "") or ""
        if section_path:
            # The heading path is part of what the chunk means ("Current limits" of which tool?).
            parts.append(f"[{doc_id}::{chunk_id}] {title} > {section_path}\n{content}")
        else:
            parts.append(f"[{doc_id}::{chunk_id}]\n{content}")

        citations.append(Citation(
            doc_id=doc_id,
            title=getattr(c, "title", "") or "",
            chunk_id=chunk_id,
            score=float(getattr(c, "score", 0.0)),
            excerpt=content[:800],
            download_url=f"/v1/documents/{quote(doc_id, safe='')}/download",
            year=getattr(c, "year", None),
            author=getattr(c, "author", None),
            source_type=getattr(c, "source_type", None),
            publisher=getattr(c, "publisher", None),
            url=getattr(c, "url", None),
            language=getattr(c, "language", None),
            identifiers=getattr(c, "identifiers", None),
        ))

    debug = {
        "selected_count": len(selected),
        "top_k": top_k,
        "max_chunks_per_doc": max_chunks_per_doc,
        "docs": len(per_doc),
    }

    return PackedContext(
        context_text="\n\n".join(parts),
        citations=citations,
        debug=debug,
    )
