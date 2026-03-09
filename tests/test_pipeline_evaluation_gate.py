from types import SimpleNamespace

import pytest

from app.rag.cases.loader import EvaluationConfig
from app.rag.planner.deterministic import PlanResult
from app.rag import pipeline


class _FakeEmbedder:
    def embed(self, query):
        return [0.1]


def _candidate():
    return SimpleNamespace(
        chunk_id="c1",
        doc_id="d1",
        ordinal=1,
        title="Doc",
        author=None,
        year=None,
        source_type="docs",
        publisher=None,
        url=None,
        language=None,
        identifiers=None,
        content="A",
        score=0.2,
        channel="vector",
    )


def _plan(enforce: bool, min_citations: int = 1):
    return PlanResult(
        filters={},
        retrieval={"top_k_vector": 5, "top_k_lexical": 5, "top_k_final": 5, "max_chunks_per_doc": 3},
        trace={"planner_mode": "deterministic"},
        prompt_instruction=None,
        case_id="docs_case",
        evaluation=EvaluationConfig(
            min_citations=min_citations,
            min_unique_docs=1,
            min_avg_score=0.0,
            enforce=enforce,
        ),
    )


def test_answer_question_adds_evaluation_gate_debug(monkeypatch):
    monkeypatch.setattr(pipeline, "plan_query", lambda *args, **kwargs: _plan(enforce=False))
    monkeypatch.setattr(pipeline, "rewrite_query_if_enabled", lambda *args, **kwargs: "q")
    monkeypatch.setattr(pipeline, "default_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(pipeline, "hybrid_retrieve", lambda *args, **kwargs: [_candidate()])
    monkeypatch.setattr(pipeline, "compose_answer", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(pipeline, "strict_grounding_check", lambda *args, **kwargs: None)

    resp = pipeline.answer_question("hei")
    assert resp.retrieval_debug is not None
    assert "evaluation_gate" in resp.retrieval_debug
    assert resp.retrieval_debug["evaluation_gate"]["passed"] is True


def test_answer_question_enforces_failed_evaluation_gate(monkeypatch):
    monkeypatch.setattr(pipeline, "plan_query", lambda *args, **kwargs: _plan(enforce=True, min_citations=2))
    monkeypatch.setattr(pipeline, "rewrite_query_if_enabled", lambda *args, **kwargs: "q")
    monkeypatch.setattr(pipeline, "default_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(pipeline, "hybrid_retrieve", lambda *args, **kwargs: [_candidate()])
    monkeypatch.setattr(pipeline, "compose_answer", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(pipeline, "strict_grounding_check", lambda *args, **kwargs: None)

    with pytest.raises(ValueError):
        pipeline.answer_question("hei")


def test_answer_question_uses_request_prompt_profile_case_id(monkeypatch):
    captured = {}

    monkeypatch.setattr(pipeline, "plan_query", lambda *args, **kwargs: _plan(enforce=False))
    monkeypatch.setattr(pipeline, "rewrite_query_if_enabled", lambda *args, **kwargs: "q")
    monkeypatch.setattr(pipeline, "default_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(pipeline, "hybrid_retrieve", lambda *args, **kwargs: [_candidate()])
    monkeypatch.setattr(pipeline, "strict_grounding_check", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pipeline,
        "resolve_effective_paths",
        lambda case_id=None: (
            f"persona:{case_id}",
            f"template:{case_id}",
            "case",
            "case",
        ),
    )

    def _fake_compose_answer(*args, **kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(pipeline, "compose_answer", _fake_compose_answer)

    resp = pipeline.answer_question("hei", prompt_profile_case_id="innovasjon_intervjuer")
    assert captured["case_id"] == "innovasjon_intervjuer"
    assert resp.retrieval_debug["query_plan"]["requested_prompt_profile_case_id"] == "innovasjon_intervjuer"
    assert resp.retrieval_debug["query_plan"]["effective_prompt_profile_case_id"] == "innovasjon_intervjuer"
