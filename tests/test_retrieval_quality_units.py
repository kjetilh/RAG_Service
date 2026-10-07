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
