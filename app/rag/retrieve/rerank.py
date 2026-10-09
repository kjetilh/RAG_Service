from __future__ import annotations
import math
from functools import lru_cache
from typing import List
from app.rag.retrieve.hybrid import RetrievedChunk
from app.settings import settings

class Reranker:
    def rerank(self, query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        raise NotImplementedError

class NoopReranker(Reranker):
    def rerank(self, query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        return sorted(chunks, key=lambda c: c.score, reverse=True)


def rerank_text(chunk: RetrievedChunk, limit: int = 1600) -> str:
    """What the cross-encoder reads: document title and heading path, then the body.
    The same text the chunk was indexed with (chunker v2)."""
    title = (getattr(chunk, "title", "") or "").replace("_", " ").strip()
    section_path = getattr(chunk, "section_path", None)
    head = title + (f" > {section_path}" if section_path else "") if title else (section_path or "")
    body = chunk.content or ""
    return (f"{head}\n{body}" if head else body)[:limit]


class CrossEncoderReranker(Reranker):
    """Re-scores the head of the fused ranking with a cross-encoder.

    Measured 2026-10-08 on the HAVEN docs (108 questions): the right document
    first went from 50 % to 76 %, at the cost of a few seconds per question on
    the host's CPU. Only the first RERANKER_TOP_N candidates are re-scored; the
    rest keep their order below them.
    Requires: pip install -e '.[emb]'
    """
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
        except Exception as e:
            raise RuntimeError("CrossEncoder reranker requires extras: pip install -e '.[emb]'") from e
        self.model = CrossEncoder(model_name, max_length=int(getattr(settings, "reranker_max_length", 384)))

    def rerank(self, query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        if not chunks:
            return chunks
        top_n = max(1, int(getattr(settings, "reranker_top_n", 30)))
        ordered = sorted(chunks, key=lambda c: c.score, reverse=True)
        head, tail = ordered[:top_n], ordered[top_n:]
        scores = self.model.predict([(query, rerank_text(c)) for c in head])  # higher is better
        return order_after_rerank(head, [float(s) for s in scores], tail)


def order_after_rerank(head: List[RetrievedChunk], scores: List[float], tail: List[RetrievedChunk]) -> List[RetrievedChunk]:
    # Logits become (0, 1): same order, and score thresholds (evaluation gate) keep their meaning.
    rescored = [RetrievedChunk(**{**c.__dict__, "score": 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, float(s)))))})
                for c, s in zip(head, scores)]
    rescored.sort(key=lambda x: x.score, reverse=True)
    if not tail:
        return rescored
    # The tail stays below the re-scored head, in its fused order, with positive scores.
    floor = min(x.score for x in rescored) * 0.5
    return rescored + [RetrievedChunk(**{**t.__dict__, "score": floor / (1.0 + i)}) for i, t in enumerate(tail)]


@lru_cache(maxsize=2)
def _cached_reranker(model_name: str) -> Reranker:
    # Loading a cross-encoder takes seconds; it used to happen on every request.
    return CrossEncoderReranker(model_name)


def default_reranker() -> Reranker:
    if bool(settings.reranker_enabled):
        return _cached_reranker(settings.reranker_model)
    return NoopReranker()
