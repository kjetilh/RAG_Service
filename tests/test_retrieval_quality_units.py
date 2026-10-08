"""Unit tests for the 2026-10-08 retrieval changes.

Each test states the property the change exists for, so a later "simplification"
that removes the property fails here instead of in production.
"""
from pathlib import Path

from app.rag.index.bm25_store import BM25Index, tokenize
from app.rag.ingest import chunker, metadata
from app.rag.retrieve import hybrid as hybrid_mod


DOC = """Intro text before any heading that says what the document is about.

# Tooling

## Read-Only MCP Adapter

It exposes resources and tools.

### Current limits

- it is lexical local lookup, not vector RAG
- it does not write notes

## Another section

""" + ("word " * 500)


def test_v2_keeps_preamble_and_heading_path(monkeypatch):
    chunks = chunker.chunk_text_v2("d", DOC, doc_title="15_Documentation_Discovery")
    assert chunks[0].content.startswith("Intro text"), "text before the first heading must not be dropped"
    limits = [c for c in chunks if "lexical local lookup" in c.content][0]
    # small sections are merged; every heading on the way survives as a label
    assert limits.index_text.startswith("15 Documentation Discovery")
    assert "Read-Only MCP Adapter" in limits.index_text and "Current limits" in limits.index_text
    big = [c for c in chunks if c.content.startswith("word word")][0]
    assert big.section_path == "Tooling > Another section"
    assert big.index_text.startswith("15 Documentation Discovery > Tooling > Another section\n")


def test_v2_merges_tiny_sections_and_bounds_long_ones():
    chunks = chunker.chunk_text_v2("d", DOC, doc_title="T")
    sizes = [len(c.content.split()) for c in chunks]
    assert max(sizes) <= 380
    # the two-bullet "Current limits" section is not a chunk of its own
    assert not any(c.content.strip().startswith("- it is lexical") and len(c.content.split()) < 20 for c in chunks)


def test_v2_never_splits_inside_a_small_code_block():
    text = "# A\n\n" + ("para " * 150) + "\n\n```swift\nlet a = 1\nlet b = 2\n```\n\n" + ("tail " * 150)
    chunks = chunker.chunk_text_v2("d", text, doc_title="T")
    assert sum(1 for c in chunks if "let a = 1" in c.content and "let b = 2" in c.content) == 1


def test_v1_is_unchanged_by_default(monkeypatch):
    monkeypatch.setattr(chunker.settings, "chunker_version", "v1")
    chunks = chunker.chunk_text("d", "# H\n\nbody text")
    assert [(c.section_path, c.content, c.index_text) for c in chunks] == [("H", "body text", None)]


def test_doc_id_v2_separates_same_name_same_content_in_two_folders(monkeypatch):
    h = metadata.compute_hash("same")
    monkeypatch.setattr(metadata.settings, "doc_id_scheme", "v1")
    assert metadata.make_doc_id(Path("/a/README.md"), h) == metadata.make_doc_id(Path("/b/README.md"), h)
    monkeypatch.setattr(metadata.settings, "doc_id_scheme", "v2")
    a, b = metadata.make_doc_id(Path("/a/README.md"), h), metadata.make_doc_id(Path("/b/README.md"), h)
    assert a != b and a.startswith("README-") and a == metadata.make_doc_id(Path("/a/README.md"), h)


def _rows(texts):
    return [{"chunk_id": f"c{i}", "doc_id": f"d{i}", "ordinal": 0, "source_type": "docs", "year": None, "text": t}
            for i, t in enumerate(texts)]


def test_bm25_answers_a_natural_language_question():
    idx = BM25Index(_rows([
        "The scaffold administrator is registered per scaffold and can delegate one hop.",
        "Flows carry FlowElement values between cells.",
        "How to build the project with swift build.",
    ]))
    ranked = idx.search("Hvordan registreres en administrator for et scaffold?", 3)
    assert ranked and ranked[0][0] == 0, "an AND query over every word would have returned nothing"


def test_bm25_splits_identifiers():
    assert {"publisheraccess", "publisher", "access", "issue"} <= set(tokenize("publisherAccess.issue"))
    idx = BM25Index(_rows(["call `publisherAccess.issue` to grant", "unrelated text about flows"]))
    assert idx.search("publisher access", 2)[0][0] == 0


def test_bm25_filter_is_applied_before_ranking():
    rows = _rows(["alpha beta", "alpha beta gamma"])
    rows[0]["source_type"] = "internal"
    idx = BM25Index(rows)
    ranked = idx.search("alpha", 5, allowed=lambda r: r["source_type"] == "docs")
    assert [i for i, _ in ranked] == [1]


def _row(cid, doc, score):
    return (cid, doc, 0, "T", None, None, "docs", None, None, None, None, "content", score, "A > B")


def test_rrf_lets_the_lexical_channel_count(monkeypatch):
    vec = [_row("v1", "d1", 0.80), _row("both", "d2", 0.70)]
    lex = [_row("both", "d2", 3.1), _row("l1", "d3", 2.0)]
    monkeypatch.setattr(hybrid_mod, "vector_search", lambda *a, **k: vec)
    monkeypatch.setattr(hybrid_mod, "lexical_search", lambda *a, **k: lex)
    monkeypatch.setattr(hybrid_mod.settings, "graph_mode", "off")

    monkeypatch.setattr(hybrid_mod.settings, "hybrid_fusion", "rrf")
    out = hybrid_mod.hybrid_retrieve("q", None, 10, 10, {})
    assert out[0].chunk_id == "both" and out[0].channel == "both"
    assert out[0].section_path == "A > B"
    assert {c.chunk_id for c in out} == {"v1", "both", "l1"}

    monkeypatch.setattr(hybrid_mod.settings, "hybrid_fusion", "max")
    out = hybrid_mod.hybrid_retrieve("q", None, 10, 10, {})
    assert out[0].chunk_id == "both" and out[0].score == 3.1, "max fusion keeps the previous behaviour"


class _Resp:
    def __init__(self, status, text):
        self.status_code, self.text, self.headers, self.reason = status, text, {}, "x"

    def raise_for_status(self):
        raise AssertionError("not reached")


def test_empty_llm_account_fails_fast_and_trips_breaker(monkeypatch):
    from app.rag.generate import llm_provider as lp
    lp.reset_llm_breaker()
    calls = []
    monkeypatch.setattr(lp.requests, "post", lambda *a, **k: calls.append(1) or _Resp(429, '{"error":{"type":"insufficient_quota"}}'))
    monkeypatch.setattr(lp.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("must not sleep/retry")))
    provider = lp.OpenAICompatibleProvider("http://x", "k", "m")
    import pytest
    with pytest.raises(lp.LLMUnavailable):
        provider._post_with_retries("http://x/chat/completions", {}, {})
    with pytest.raises(lp.LLMUnavailable):
        provider._post_with_retries("http://x/chat/completions", {}, {})
    assert len(calls) == 1, "second call must be stopped by the breaker, without a request"
    lp.reset_llm_breaker()


def test_ordinary_rate_limit_is_still_retried(monkeypatch):
    from app.rag.generate import llm_provider as lp
    lp.reset_llm_breaker()
    seq = [_Resp(429, "rate limit, slow down"), _Resp(200, "ok")]
    monkeypatch.setattr(lp.requests, "post", lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(lp.time, "sleep", lambda s: None)
    r = lp.OpenAICompatibleProvider("http://x", "k", "m")._post_with_retries("http://x", {}, {})
    assert r.status_code == 200 and lp.llm_unavailable_reason() is None


def test_link_graph_resolves_relative_links_and_file_mentions():
    from app.rag.retrieve.graph_expand import build_link_graph
    docs = [
        {"doc_id": "a", "file_path": "/data/Book/04_Agreements.md", "text": "see [flows](05_Flows.md#x) and `Gap_Analysis.md`"},
        {"doc_id": "b", "file_path": "/data/Book/05_Flows.md", "text": "no links"},
        {"doc_id": "c", "file_path": "/data/Gap_Analysis.md", "text": "[ext](https://example.org/05_Flows.md)"},
        {"doc_id": "d", "file_path": "/data/x/README.md", "text": "README.md twice"},
        {"doc_id": "e", "file_path": "/data/y/README.md", "text": ""},
    ]
    g = build_link_graph(docs)
    assert g["a"]["b"] >= 1.0 and g["b"]["a"] > 0
    assert g["a"]["c"] == 0.6
    assert "b" not in g.get("c", {}), "external links are not edges"
    assert "e" not in g.get("d", {}), "an ambiguous file name is not an edge"


def test_reserved_slots_never_move_the_ranking_above_them(monkeypatch):
    from types import SimpleNamespace
    from app.rag.retrieve import pack_context as pc
    from app.rag.retrieve import graph_expand

    cands = pc.CandidateList(
        SimpleNamespace(chunk_id=f"c{i}", doc_id=f"d{i}", ordinal=0, content="x", score=1.0 - i * 0.01, title="T")
        for i in range(12)
    )
    cands.query_emb, cands.filters = [0.1], {}
    linked = [("g1", "dlinked", 0, "T", None, None, "docs", None, None, None, None, "linked text", 0.4, "S")]
    monkeypatch.setattr(graph_expand, "linked_document_chunks", lambda *a, **k: linked)

    monkeypatch.setattr(pc, "_graph_mode", lambda: "off", raising=False)
    from app.settings import settings
    monkeypatch.setattr(settings, "graph_mode", "off")
    plain = [c.chunk_id for c in pc.pack_context(cands, top_k=6, max_chunks_per_doc=3).citations]
    monkeypatch.setattr(settings, "graph_mode", "expand")
    expanded = [c.chunk_id for c in pc.pack_context(cands, top_k=6, max_chunks_per_doc=3).citations]
    assert plain == ["c0", "c1", "c2", "c3", "c4", "c5"]
    assert expanded == ["c0", "c1", "c2", "c3", "c4", "g1"], "top places unchanged, linked document last"

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(graph_expand, "linked_document_chunks", boom)
    assert [c.chunk_id for c in pc.pack_context(cands, top_k=6, max_chunks_per_doc=3).citations] == plain


def test_rerank_reads_title_and_heading_path_and_keeps_tail_below():
    from app.rag.retrieve import rerank as rr
    mk = lambda cid, score, sp=None: hybrid_mod.RetrievedChunk(cid, "d", 0, "15_Doc_Title", None, None, "docs", None, None, None, None, "body", score, "vector", sp)
    assert rr.rerank_text(mk("a", 1.0, "Limits > Current")) == "15 Doc Title > Limits > Current\nbody"
    out = rr.order_after_rerank([mk("a", 0.9), mk("b", 0.8)], [-3.0, 5.0], [mk("t1", 0.7), mk("t2", 0.6)])
    assert [c.chunk_id for c in out] == ["b", "a", "t1", "t2"]
    assert out[2].score < out[1].score and out[3].score < out[2].score


def test_reranker_model_is_loaded_once(monkeypatch):
    from app.rag.retrieve import rerank as rr
    made = []

    class Fake(rr.Reranker):
        def __init__(self, name):
            made.append(name)

    rr._cached_reranker.cache_clear()
    monkeypatch.setattr(rr, "CrossEncoderReranker", Fake)
    monkeypatch.setattr(rr.settings, "reranker_enabled", True)
    a, b = rr.default_reranker(), rr.default_reranker()
    assert a is b and len(made) == 1
    rr._cached_reranker.cache_clear()


def test_rerank_is_bounded_and_can_be_skipped(monkeypatch):
    from app.rag import pipeline

    class Fake:
        def rerank(self, query, chunks):
            return list(reversed(chunks))

    monkeypatch.setattr(pipeline, "default_reranker", lambda: Fake())
    monkeypatch.setattr(pipeline.settings, "reranker_enabled", False)
    assert pipeline._maybe_rerank("q", [1, 2], None) == ([1, 2], "off")
    monkeypatch.setattr(pipeline.settings, "reranker_enabled", True)
    assert pipeline._maybe_rerank("q", [1, 2], None) == ([2, 1], "applied")
    assert pipeline._maybe_rerank("q", [1, 2], False) == ([1, 2], "skipped_by_request")
    # a second request while one re-ranking runs gets the fused ranking, it does not queue
    assert pipeline._RERANK_SEM.acquire(blocking=False)
    try:
        assert pipeline._maybe_rerank("q", [1, 2], None) == ([1, 2], "skipped_busy")
    finally:
        pipeline._RERANK_SEM.release()

    class Broken:
        def rerank(self, query, chunks):
            raise RuntimeError("model missing")

    monkeypatch.setattr(pipeline, "default_reranker", lambda: Broken())
    assert pipeline._maybe_rerank("q", [1, 2], None) == ([1, 2], "skipped_error")
    assert pipeline._RERANK_SEM.acquire(blocking=False), "the slot must be released after an error"
    pipeline._RERANK_SEM.release()


def test_retrieval_config_route_exposes_settings_but_no_secrets():
    from fastapi.testclient import TestClient
    from app.main import app
    body = TestClient(app).get("/v1/retrieval/config").json()
    assert {"embedding_model", "chunker_version", "hybrid_fusion", "lexical_mode", "reranker_enabled", "warm_up"} <= set(body)
    text = str(body).lower()
    assert "api_key" not in text and "database_url" not in text and "secret" not in text
