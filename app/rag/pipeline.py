from __future__ import annotations

from typing import Any, Dict, Optional, Iterable
import json
from threading import Semaphore

from app.settings import settings
from app.models.schemas import ChatResponse, Citation
from app.rag.index.embedder import default_embedder
from app.rag.retrieve.hybrid import hybrid_retrieve
from app.rag.retrieve.rerank import default_reranker
from app.rag.retrieve.pack_context import pack_context
from app.rag.generate.composer import compose_answer, rewrite_query_if_enabled
from app.rag.safety.grounding import strict_grounding_check

# Global throttle to avoid parallel LLM calls from the UI (double-submit / reconnect / multiple tabs).
_LLM_SEM = Semaphore(1)


def _map_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    internal: Dict[str, Any] = {}
    if "year" in filters and isinstance(filters["year"], dict) and "gte" in filters["year"]:
        internal["year_gte"] = filters["year"]["gte"]
    if "source_type" in filters and isinstance(filters["source_type"], list):
        internal["source_type"] = filters["source_type"]
    return internal


def answer_question(
    message: str,
    conversation_id: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    top_k: Optional[int] = None,
    model_profile: Optional[str] = None,
) -> ChatResponse:
    filters = filters or {}
    internal_filters = _map_filters(filters)

    # Rewrite (optional)
    query = rewrite_query_if_enabled(message, model_profile=model_profile)

    # Embed query
    embedder = default_embedder()
    query_emb = embedder.embed(query)

    # Retrieve candidates
    candidates = hybrid_retrieve(
        query=query,
        query_emb=query_emb,
        top_k_vector=max(10, int((top_k or 50) * 0.7)),
        top_k_lexical=max(10, int((top_k or 50) * 0.7)),
        filters=internal_filters,
    )

    # Rerank (optional)
    if settings.reranker_enabled:
        reranker = default_reranker()
        candidates = reranker.rerank(query, candidates, top_k=int(top_k or 50))

    # Pack context (and also build citations)
    packed = pack_context(candidates, int(top_k or 50))

    # Compose answer with concurrency throttle
    with _LLM_SEM:
        answer = compose_answer(message, packed, model_profile=model_profile)

    # Grounding gate (optional but recommended)
    citations = packed.citations
    strict_grounding_check(answer, citations)

    return ChatResponse(answer=answer, citations=citations, retrieval_debug=packed.debug)


def answer_question_stream(
    message: str,
    conversation_id: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    top_k: Optional[int] = None,
    model_profile: Optional[str] = None,
) -> Iterable[bytes]:
    """SSE stream.
    Events:
      - citations: JSON list
      - delta: {delta: "..."}
      - error: {message: "...", type?: "..."}
      - done
    """
    try:
        resp = answer_question(message, conversation_id, filters or {}, top_k, model_profile=model_profile)

        # Send citations first
        citations_payload = json.dumps([c.model_dump() for c in resp.citations], ensure_ascii=False)
        yield f"event: citations\ndata: {citations_payload}\n\n".encode("utf-8")

        # Stream answer in chunks (server-side chunking)
        chunk_size = max(10, int(settings.stream_chunk_chars))
        text = resp.answer or ""
        for i in range(0, len(text), chunk_size):
            piece = text[i:i + chunk_size]
            data = json.dumps({"delta": piece}, ensure_ascii=False)
            yield f"event: delta\ndata: {data}\n\n".encode("utf-8")

        yield b"event: done\ndata: {}\n\n"
        return

    except Exception as e:
        # Do not crash the SSE stream with a stack trace; send a structured error.
        payload = json.dumps(
            {
                "message": str(e),
                "type": e.__class__.__name__,
                "hint": "If this is a 429 from OpenAI, retry after a short delay or reduce concurrent requests.",
            },
            ensure_ascii=False,
        )
        yield f"event: error\ndata: {payload}\n\n".encode("utf-8")
        yield b"event: done\ndata: {}\n\n"
