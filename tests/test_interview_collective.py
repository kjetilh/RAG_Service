from pathlib import Path

import pytest

from app.api import routes_interviews
from app.api.routes_interviews import CollectiveSummaryRequest
from app.models.schemas import ChatResponse, Citation
from app.rag.interviews.collective import (
    InterviewQuestion,
    PreparedQuestionSet,
    build_collective_summary,
    prepare_question_set,
)


def _ok_response(answer: str) -> ChatResponse:
    return ChatResponse(
        answer=answer,
        citations=[
            Citation(
                doc_id="d1",
                title="Doc 1",
                chunk_id="d1-c1",
                score=0.9,
                excerpt="x",
            )
        ],
        retrieval_debug={"query_plan": {"planner_mode": "deterministic"}},
    )


def test_prepare_question_set_from_inline():
    prepared = prepare_question_set(
        inline_questions=[
            {"question_id": "Q1", "text": "Hva er viktigst?"},
            {"question_id": "Q2", "text": "Hva er vanskeligst?"},
        ],
        question_set_path=None,
        question_set_id="intervju-v1",
    )
    assert prepared.source == "inline"
    assert prepared.question_set_id == "intervju-v1"
    assert [q.question_id for q in prepared.questions] == ["Q1", "Q2"]


def test_prepare_question_set_rejects_duplicate_inline_ids():
    with pytest.raises(ValueError):
        prepare_question_set(
            inline_questions=[
                {"question_id": "Q1", "text": "A"},
                {"question_id": "Q1", "text": "B"},
            ],
            question_set_path=None,
            question_set_id=None,
        )


def test_prepare_question_set_from_file():
    repo_root = Path(__file__).resolve().parents[1]
    p = repo_root / ".tmp_interview_questions_test.yml"
    p.write_text(
        """
version: 1
question_set_id: intervju_test
language: nb
questions:
  - question_id: Q1
    text: Første spørsmål
  - question_id: Q2
    text: Andre spørsmål
""".strip(),
        encoding="utf-8",
    )
    try:
        prepared = prepare_question_set(
            inline_questions=None,
            question_set_path=str(p),
            question_set_id=None,
        )
        assert prepared.source == "file"
        assert prepared.question_set_id == "intervju_test"
        assert len(prepared.questions) == 2
    finally:
        p.unlink(missing_ok=True)


def test_build_collective_summary_runs_each_question():
    prepared = PreparedQuestionSet(
        question_set_id="set-1",
        source="inline",
        source_path=None,
        questions=[
            InterviewQuestion(question_id="Q1", text="Hva mener de om A?"),
            InterviewQuestion(question_id="Q2", text="Hva mener de om B?"),
        ],
    )

    captured = []

    def _fake_run(req):
        captured.append(req)
        return _ok_response(answer=f"answer:{req.query}")

    summary = build_collective_summary(
        case_id="innovasjon_intervjuer",
        prompt_profile_case_id="innovasjon_bokskriving",
        question_set=prepared,
        filters={"source_type": ["innovasjon_intervju_transcript"]},
        top_k=10,
        model_profile="gpt-4o-mini",
        run_query_fn=_fake_run,
    )

    assert len(captured) == 2
    assert all(req.case_id == "innovasjon_intervjuer" for req in captured)
    assert all(req.prompt_profile_case_id == "innovasjon_bokskriving" for req in captured)
    assert all(req.model_profile == "gpt-4o-mini" for req in captured)
    assert all(req.filters["source_type"] == ["innovasjon_intervju_transcript"] for req in captured)
    assert summary.question_count == 2
    assert summary.succeeded_count == 2
    assert summary.failed_count == 0
    assert all(item.status == "ok" for item in summary.items)


def test_build_collective_summary_captures_per_question_errors():
    prepared = PreparedQuestionSet(
        question_set_id="set-1",
        source="inline",
        source_path=None,
        questions=[InterviewQuestion(question_id="Q1", text="Hva mener de om A?")],
    )

    def _always_fail(_req):
        raise RuntimeError("upstream error")

    summary = build_collective_summary(
        case_id="innovasjon_intervjuer",
        prompt_profile_case_id=None,
        question_set=prepared,
        filters=None,
        top_k=None,
        model_profile=None,
        run_query_fn=_always_fail,
    )

    assert summary.succeeded_count == 0
    assert summary.failed_count == 1
    assert summary.items[0].status == "error"
    assert "upstream error" in (summary.items[0].error or "")


def test_interviews_collective_summary_route_delegates(monkeypatch):
    monkeypatch.setattr(routes_interviews, "validate_model_profile", lambda _profile: None)

    prepared = PreparedQuestionSet(
        question_set_id="set-1",
        source="inline",
        source_path=None,
        questions=[InterviewQuestion(question_id="Q1", text="A")],
    )
    monkeypatch.setattr(routes_interviews, "prepare_question_set", lambda **_kwargs: prepared)

    captured = {}

    def _fake_build(**kwargs):
        captured.update(kwargs)
        return build_collective_summary(
            case_id=kwargs["case_id"],
            prompt_profile_case_id=kwargs["prompt_profile_case_id"],
            question_set=kwargs["question_set"],
            filters=kwargs["filters"],
            top_k=kwargs["top_k"],
            model_profile=kwargs["model_profile"],
            run_query_fn=lambda _req: _ok_response("ok"),
        )

    monkeypatch.setattr(routes_interviews, "build_collective_summary", _fake_build)

    response = routes_interviews.interviews_collective_summary(
        CollectiveSummaryRequest(
            case_id="innovasjon_intervjuer",
            prompt_profile_case_id="innovasjon_bokskriving",
            questions=[InterviewQuestion(question_id="Q1", text="A")],
            top_k=12,
            model_profile="gpt-4o-mini",
        )
    )
    assert captured["case_id"] == "innovasjon_intervjuer"
    assert captured["prompt_profile_case_id"] == "innovasjon_bokskriving"
    assert response.question_set_id == "set-1"
    assert response.succeeded_count == 1
