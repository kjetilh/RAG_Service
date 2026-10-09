from __future__ import annotations
from dataclasses import dataclass, replace
import numpy as np
from app.rag.index.vector_store import vector_search
from app.rag.index.lexical_store import lexical_search
from app.settings import settings

@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    ordinal: int
    title: str
    author: str | None
    year: int | None
    source_type: str | None
    publisher: str | None
    url: str | None
    language: str | None
    identifiers: dict | None
    content: str
    score: float
    channel: str
    section_path: str | None = None

def _row_to_chunk(r, channel: str) -> RetrievedChunk:
    # Support both old and new row shapes
    # Old:  [chunk_id, doc_id, title, author, year, source_type, content, score]
    # Mid:  [chunk_id, doc_id, ordinal, title, author, year, source_type, content, score]
    # New:  [chunk_id, doc_id, ordinal, title, author, year, source_type, publisher, url, language, identifiers, content, score]
    if len(r) == 8:
        return RetrievedChunk(
            chunk_id=r[0],
            doc_id=r[1],
            ordinal=0,
            title=r[2],
            author=r[3],
            year=r[4],
            source_type=r[5],
            publisher=None,
            url=None,
            language=None,
            identifiers=None,
            content=r[6],
            score=float(r[7]),
            channel=channel,
        )
    elif len(r) == 9:
        return RetrievedChunk(
            chunk_id=r[0],
            doc_id=r[1],
            ordinal=int(r[2] or 0),
            title=r[3],
            author=r[4],
            year=r[5],
            source_type=r[6],
            publisher=None,
            url=None,
            language=None,
            identifiers=None,
            content=r[7],
            score=float(r[8]),
            channel=channel,
        )
    elif len(r) >= 13:
        return RetrievedChunk(
            chunk_id=r[0],
            doc_id=r[1],
            ordinal=int(r[2] or 0),
            title=r[3],
            author=r[4],
            year=r[5],
            source_type=r[6],
            publisher=r[7],
            url=r[8],
            language=r[9],
            identifiers=r[10],
            content=r[11],
            score=float(r[12]),
            channel=channel,
            section_path=(r[13] if len(r) >= 14 else None),
        )
    else:
        raise ValueError(f"Unexpected row length={len(r)} for {channel}: {r}")


def _deterministic_sort_key(chunk: RetrievedChunk):
    return (
        -float(chunk.score),
        str(chunk.doc_id),
        int(chunk.ordinal),
        str(chunk.chunk_id),
        str(chunk.channel),
    )


def _fuse_max(vec_chunks: list[RetrievedChunk], lex_chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    best: dict[str, RetrievedChunk] = {}
    for c in vec_chunks + lex_chunks:
        if c.chunk_id not in best:
            best[c.chunk_id] = c
            continue
        prev = best[c.chunk_id]
        if float(c.score) > float(prev.score):
            best[c.chunk_id] = c
        elif float(c.score) == float(prev.score):
            if _deterministic_sort_key(c) < _deterministic_sort_key(prev):
                best[c.chunk_id] = c
    return sorted(best.values(), key=_deterministic_sort_key)


def _fuse_rrf(vec_chunks: list[RetrievedChunk], lex_chunks: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
    """Reciprocal rank fusion.

    Cosine similarity (0..1) and a lexical score live on different scales, so
    taking the larger raw score lets the vector channel decide alone. RRF only
    uses each channel's ranking: score = sum(1 / (k + rank)).
    """
    fused: dict[str, float] = {}
    first: dict[str, RetrievedChunk] = {}
    channels: dict[str, set[str]] = {}
    for ranking in (vec_chunks, lex_chunks):
        for rank, c in enumerate(ranking):
            fused[c.chunk_id] = fused.get(c.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            first.setdefault(c.chunk_id, c)
            channels.setdefault(c.chunk_id, set()).add(c.channel)
    out: list[RetrievedChunk] = []
    for chunk_id, score in fused.items():
        c = first[chunk_id]
        ch = channels[chunk_id]
        out.append(replace(c, score=float(score), channel="both" if len(ch) > 1 else next(iter(ch))))
    return sorted(out, key=_deterministic_sort_key)


def hybrid_retrieve(query: str, query_emb: np.ndarray, top_k_vector: int, top_k_lexical: int, filters: dict):
    vec_rows = vector_search(query_emb, top_k=top_k_vector, filters=filters)
    lex_rows = lexical_search(query, top_k=top_k_lexical, filters=filters)
    vec_chunks = [_row_to_chunk(r, "vector") for r in vec_rows]
    lex_chunks = [_row_to_chunk(r, "lexical") for r in lex_rows]

    if str(getattr(settings, "hybrid_fusion", "max")).lower() == "rrf":
        fused = _fuse_rrf(vec_chunks, lex_chunks, int(getattr(settings, "rrf_k", 60)))
    else:
        fused = _fuse_max(vec_chunks, lex_chunks)
    return fused
