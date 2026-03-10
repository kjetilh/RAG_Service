from __future__ import annotations
from functools import lru_cache

import numpy as np
from app.settings import settings

class Embedder:
    def embed(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

class SentenceTransformersEmbedder(Embedder):
    def __init__(self, model_name: str):
        self.model = _load_sentence_transformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)


@lru_cache(maxsize=4)
def _load_sentence_transformer(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as e:
        raise RuntimeError("Install embeddings deps: pip install -e '.[emb]'") from e
    return SentenceTransformer(model_name)


@lru_cache(maxsize=4)
def _cached_embedder(model_name: str) -> Embedder:
    return SentenceTransformersEmbedder(model_name)


def default_embedder() -> Embedder:
    return _cached_embedder(settings.embedding_model)
