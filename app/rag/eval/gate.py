from __future__ import annotations

from typing import Any

from app.rag.cases.loader import EvaluationConfig


def _round(value: float) -> float:
    return round(float(value), 6)


def run_evaluation_gate(
    citations: list[Any],
    evaluation: EvaluationConfig | None,
) -> dict[str, Any]:
    if evaluation is None:
        return {
            "passed": True,
            "enforced": False,
            "thresholds": None,
            "metrics": {
                "citation_count": len(citations),
                "unique_doc_count": len({str(getattr(c, "doc_id", "")) for c in citations}),
                "avg_score": _round(
                    (sum(float(getattr(c, "score", 0.0)) for c in citations) / len(citations))
                    if citations
                    else 0.0
                ),
            },
            "violations": [],
        }

    citation_count = len(citations)
    unique_doc_count = len({str(getattr(c, "doc_id", "")) for c in citations})
    avg_score = (
        sum(float(getattr(c, "score", 0.0)) for c in citations) / float(citation_count)
        if citation_count > 0
        else 0.0
    )
    avg_score = _round(avg_score)

    thresholds = {
        "min_citations": int(evaluation.min_citations),
        "min_unique_docs": int(evaluation.min_unique_docs),
        "min_avg_score": _round(float(evaluation.min_avg_score)),
    }
    metrics = {
        "citation_count": citation_count,
        "unique_doc_count": unique_doc_count,
        "avg_score": avg_score,
    }

    violations: list[dict[str, Any]] = []
    if citation_count < thresholds["min_citations"]:
        violations.append(
            {
                "rule": "min_citations",
                "expected_gte": thresholds["min_citations"],
                "actual": citation_count,
            }
        )
    if unique_doc_count < thresholds["min_unique_docs"]:
        violations.append(
            {
                "rule": "min_unique_docs",
                "expected_gte": thresholds["min_unique_docs"],
                "actual": unique_doc_count,
            }
        )
    if avg_score < thresholds["min_avg_score"]:
        violations.append(
            {
                "rule": "min_avg_score",
                "expected_gte": thresholds["min_avg_score"],
                "actual": avg_score,
            }
        )

    return {
        "passed": len(violations) == 0,
        "enforced": bool(evaluation.enforce),
        "thresholds": thresholds,
        "metrics": metrics,
        "violations": violations,
    }
