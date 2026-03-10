from app.rag.index import embedder


class _FakeModel:
    def encode(self, texts, normalize_embeddings=True):
        return [[0.1] for _ in texts]


def test_default_embedder_reuses_cached_model(monkeypatch):
    calls = []

    embedder._cached_embedder.cache_clear()
    embedder._load_sentence_transformer.cache_clear()

    def _fake_loader(model_name):
        calls.append(model_name)
        return _FakeModel()

    monkeypatch.setattr(embedder, "_load_sentence_transformer", _fake_loader)

    e1 = embedder.default_embedder()
    e2 = embedder.default_embedder()

    assert e1 is e2
    assert calls == [embedder.settings.embedding_model]
