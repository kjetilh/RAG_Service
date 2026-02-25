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


def pack_context(candidates, top_k: int, max_chunks_per_doc: int = 4) -> PackedContext:
    # candidates: list[RetrievedChunk] (fra hybrid_retrieve / reranker)
    # Vi gjør en enkel, robust default-selection:
    selected = []
    per_doc: Dict[str, int] = {}

    for c in sorted(candidates, key=lambda x: float(getattr(x, "score", 0.0)), reverse=True):
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

    # Bygg context + citations
    parts: List[str] = []
    citations: List[Citation] = []

    for c in selected:
        chunk_id = getattr(c, "chunk_id", "")
        doc_id = getattr(c, "doc_id", "")
        content = getattr(c, "content", "") or ""
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
