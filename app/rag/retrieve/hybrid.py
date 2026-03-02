from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from app.rag.index.vector_store import vector_search
from app.rag.index.lexical_store import lexical_search

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


def hybrid_retrieve(query: str, query_emb: np.ndarray, top_k_vector: int, top_k_lexical: int, filters: dict):
    vec_rows = vector_search(query_emb, top_k=top_k_vector, filters=filters)
    lex_rows = lexical_search(query, top_k=top_k_lexical, filters=filters)

    out: list[RetrievedChunk] = []
    for r in vec_rows:
        out.append(_row_to_chunk(r, "vector"))
    for r in lex_rows:
        out.append(_row_to_chunk(r, "lexical"))

    best: dict[str, RetrievedChunk] = {}
    for c in out:
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
