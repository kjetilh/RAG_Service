from types import SimpleNamespace

from app.rag.retrieve import hybrid as hybrid_mod
from app.rag.retrieve.pack_context import pack_context


def test_pack_context_uses_deterministic_tie_break():
    candidates = [
        SimpleNamespace(chunk_id="c2", doc_id="d1", ordinal=2, content="b", score=1.0, title="T"),
        SimpleNamespace(chunk_id="c1", doc_id="d1", ordinal=1, content="a", score=1.0, title="T"),
        SimpleNamespace(chunk_id="c3", doc_id="d0", ordinal=1, content="c", score=1.0, title="T"),
    ]
    packed = pack_context(candidates, top_k=3, max_chunks_per_doc=3)
    assert [c.chunk_id for c in packed.citations] == ["c3", "c1", "c2"]


def test_hybrid_retrieve_is_deterministic_for_ties(monkeypatch):
    vec_rows = [
        ("c1", "d1", 1, "T1", None, None, "docs", None, None, None, None, "A", 0.9),
        ("c2", "d1", 2, "T1", None, None, "docs", None, None, None, None, "B", 0.9),
    ]
    lex_rows = [
        ("c2", "d1", 2, "T1", None, None, "docs", None, None, None, None, "B", 0.9),
        ("c3", "d0", 1, "T0", None, None, "docs", None, None, None, None, "C", 0.9),
    ]
    monkeypatch.setattr(hybrid_mod, "vector_search", lambda *args, **kwargs: vec_rows)
    monkeypatch.setattr(hybrid_mod, "lexical_search", lambda *args, **kwargs: lex_rows)

    out = hybrid_mod.hybrid_retrieve(query="q", query_emb=None, top_k_vector=10, top_k_lexical=10, filters={})
    assert [c.chunk_id for c in out] == ["c3", "c1", "c2"]
