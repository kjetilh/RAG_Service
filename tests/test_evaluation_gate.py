from types import SimpleNamespace

from app.rag.cases.loader import EvaluationConfig
from app.rag.eval.gate import run_evaluation_gate


def _cit(doc_id: str, score: float):
    return SimpleNamespace(doc_id=doc_id, score=score)


def test_run_evaluation_gate_passes_when_thresholds_met():
    cfg = EvaluationConfig(min_citations=2, min_unique_docs=2, min_avg_score=0.5, enforce=False)
    citations = [_cit("d1", 0.9), _cit("d2", 0.8)]
    out = run_evaluation_gate(citations, cfg)
    assert out["passed"] is True
    assert out["metrics"]["citation_count"] == 2
    assert out["metrics"]["unique_doc_count"] == 2
    assert out["violations"] == []


def test_run_evaluation_gate_fails_when_thresholds_not_met():
    cfg = EvaluationConfig(min_citations=3, min_unique_docs=2, min_avg_score=0.7, enforce=True)
    citations = [_cit("d1", 0.6), _cit("d1", 0.4)]
    out = run_evaluation_gate(citations, cfg)
    assert out["passed"] is False
    assert out["enforced"] is True
    rules = [v["rule"] for v in out["violations"]]
    assert "min_citations" in rules
    assert "min_unique_docs" in rules
    assert "min_avg_score" in rules


def test_run_evaluation_gate_handles_none_config():
    citations = [_cit("d1", 0.5)]
    out = run_evaluation_gate(citations, None)
    assert out["passed"] is True
    assert out["enforced"] is False
    assert out["thresholds"] is None
