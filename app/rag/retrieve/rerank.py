from __future__ import annotations
from typing import List
from app.rag.retrieve.hybrid import RetrievedChunk
from app.settings import settings

class Reranker:
    def rerank(self, query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        raise NotImplementedError

class NoopReranker(Reranker):
    def rerank(self, query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        return sorted(chunks, key=lambda c: c.score, reverse=True)

class CrossEncoderReranker(Reranker):
    """Optional reranker using sentence-transformers CrossEncoder.
    Requires: pip install -e '.[emb]'
    """
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
        except Exception as e:
            raise RuntimeError("CrossEncoder reranker requires extras: pip install -e '.[emb]'") from e
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        if not chunks:
            return chunks
        pairs = [(query, c.content) for c in chunks]
        scores = self.model.predict(pairs)  # higher is better
        # Combine with existing score as a small prior
        out = []
        for c, s in zip(chunks, scores):
            c2 = RetrievedChunk(
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                title=c.title,
                author=c.author,
                year=c.year,
                source_type=c.source_type,
                content=c.content,
                score=float(0.20 * c.score + 0.80 * float(s)),
                channel=c.channel,
            )
            out.append(c2)
        return sorted(out, key=lambda x: x.score, reverse=True)

def default_reranker() -> Reranker:
    if bool(settings.reranker_enabled):
        return CrossEncoderReranker(settings.reranker_model)
    return NoopReranker()
