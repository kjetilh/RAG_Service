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
        # Only the head is re-scored; a cross-encoder call per candidate is the
        # expensive part of a request.
        top_n = max(1, int(getattr(settings, "reranker_top_n", 30)))
        ordered = sorted(chunks, key=lambda c: c.score, reverse=True)
        chunks, tail = ordered[:top_n], ordered[top_n:]
        pairs = [(query, c.content) for c in chunks]
        scores = self.model.predict(pairs)  # higher is better
        # Combine with existing score as a small prior
        out = []
        for c, s in zip(chunks, scores):
            c2 = RetrievedChunk(
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                ordinal=c.ordinal,
                title=c.title,
                author=c.author,
                year=c.year,
                source_type=c.source_type,
                publisher=c.publisher,
                url=c.url,
                language=c.language,
                identifiers=c.identifiers,
                content=c.content,
                score=float(s),
                channel=c.channel,
                section_path=getattr(c, "section_path", None),
            )
            out.append(c2)
        head = sorted(out, key=lambda x: x.score, reverse=True)
        if not tail:
            return head
        # Keep the tail below the re-scored head whatever scale the model uses.
        floor = min(x.score for x in head) - 1.0
        return head + [
            RetrievedChunk(**{**t.__dict__, "score": floor - i * 1e-6}) for i, t in enumerate(tail)
        ]

def default_reranker() -> Reranker:
    if bool(settings.reranker_enabled):
        return CrossEncoderReranker(settings.reranker_model)
    return NoopReranker()
