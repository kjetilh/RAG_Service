from __future__ import annotations
import numpy as np
from app.settings import settings

class Embedder:
    def embed(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

class SentenceTransformersEmbedder(Embedder):
    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as e:
            raise RuntimeError("Install embeddings deps: pip install -e '.[emb]'") from e
        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)

def default_embedder() -> Embedder:
    return SentenceTransformersEmbedder(settings.embedding_model)
