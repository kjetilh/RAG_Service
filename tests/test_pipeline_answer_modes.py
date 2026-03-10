from types import SimpleNamespace

from app.models.schemas import ChatResponse, Citation
from app.rag.cases.loader import EvaluationConfig
from app.rag.interviews.collective import CollectiveSummaryItem, CollectiveSummaryResponse
from app.rag.planner.answer_modes import AnswerModePlan, GENERAL_DIRECT_CONTRACT
from app.rag.planner.deterministic import PlanResult
from app.rag import pipeline


def _citation(idx: int) -> Citation:
    return Citation(
        doc_id=f"d{idx}",
        title=f"Doc {idx}",
        chunk_id=f"c{idx}",
        score=0.9 - (idx * 0.01),
        excerpt=f"Dette er sitat {idx} fra materialet.",
    )


def _plan(answer_mode: AnswerModePlan) -> PlanResult:
    return PlanResult(
        filters={"source_type": ["innovasjonsledelse", "innovasjon_intervju_transcript"]},
        retrieval={"top_k_vector": 5, "top_k_lexical": 5, "top_k_final": 5, "max_chunks_per_doc": 3},
        trace={"planner_mode": "deterministic", **answer_mode.as_trace()},
        prompt_instruction=None,
        case_id="innovasjon_bokskriving",
        evaluation=EvaluationConfig(min_citations=1, min_unique_docs=1, min_avg_score=0.0, enforce=False),
        answer_mode=answer_mode,
    )


def test_answer_question_formats_interview_findings_per_question(monkeypatch):
    mode = AnswerModePlan(
        answer_mode="interview_findings_per_question",
        source_strategy="interviews",
        response_shape="question_matrix",
        streaming_allowed=False,
        rewrite_query=False,
        use_subquery_planner=False,
        default_prompt_case_id="innovasjon_intervjuer",
        question_set_path="config/interview_questions_innovasjonspolitikk.yml",
    )
    monkeypatch.setattr(pipeline, "plan_query", lambda *_args, **_kwargs: _plan(mode))
    monkeypatch.setattr(
        pipeline,
        "prepare_question_set",
        lambda **_kwargs: SimpleNamespace(question_set_id="qs-1", questions=[]),
    )
    monkeypatch.setattr(
        pipeline,
        "build_collective_summary",
        lambda **_kwargs: CollectiveSummaryResponse(
            case_id="innovasjon_intervjuer",
            question_set_id="qs-1",
            question_count=1,
            succeeded_count=1,
            failed_count=0,
            items=[
                CollectiveSummaryItem(
                    question_id="Q1",
                    question="Hva fungerer?",
                    status="ok",
                    answer="Dette er hovedfunnet [1][2].",
                    citations=[_citation(1), _citation(2), _citation(3), _citation(4)],
                    citation_count=4,
                    unique_doc_count=4,
                )
            ],
        ),
    )

    resp = pipeline.answer_question("Hva er funnene pr spørsmål?")

    assert "## Funn per spørsmål" in resp.answer
    assert "### Q1. Hva fungerer?" in resp.answer
    assert "Dette er hovedfunnet" in resp.answer
    assert "[1]" in resp.answer and "[2]" in resp.answer and "[3]" in resp.answer
    assert "[4]" not in resp.answer
    assert resp.retrieval_debug["query_plan"]["answer_mode"] == "interview_findings_per_question"


def test_answer_question_formats_per_interview_summary(monkeypatch):
    mode = AnswerModePlan(
        answer_mode="interview_summary_per_interview",
        source_strategy="interviews",
        response_shape="per_interview",
        streaming_allowed=False,
        rewrite_query=False,
        use_subquery_planner=False,
        default_prompt_case_id="innovasjon_intervjuer",
    )
    monkeypatch.setattr(
        pipeline,
        "plan_query",
        lambda _message, filters=None: PlanResult(
            filters=filters or {"source_type": ["innovasjon_intervju_transcript"]},
            retrieval={"top_k_vector": 5, "top_k_lexical": 5, "top_k_final": 5, "max_chunks_per_doc": 3},
            trace={"planner_mode": "deterministic", **mode.as_trace()},
            prompt_instruction=None,
            case_id="innovasjon_bokskriving",
            evaluation=EvaluationConfig(min_citations=1, min_unique_docs=1, min_avg_score=0.0, enforce=False),
            answer_mode=mode,
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "_list_documents",
        lambda *_args, **_kwargs: [
            {"doc_id": "d1", "title": "Intervju A", "source_type": "innovasjon_intervju_transcript"},
            {"doc_id": "d2", "title": "Intervju B", "source_type": "innovasjon_intervju_transcript"},
        ],
    )

    def _fake_run_planned_single_pass(**kwargs):
        doc_id = kwargs["plan"].filters["doc_id"][0]
        return ChatResponse(
            answer=f"Oppsummering for {doc_id} [1]",
            citations=[_citation(1)],
            retrieval_debug={"query_plan": {"selected_case": "innovasjon_intervjuer"}},
        )

    monkeypatch.setattr(pipeline, "_run_planned_single_pass", _fake_run_planned_single_pass)

    resp = pipeline.answer_question("Oppsummering pr intervju")

    assert "## Oppsummering per intervju" in resp.answer
    assert "### Intervju A" in resp.answer
    assert "### Intervju B" in resp.answer
    assert len(resp.citations) == 2
    assert resp.retrieval_debug["query_plan"]["answer_mode"] == "interview_summary_per_interview"


def test_answer_question_passes_dynamic_contract_for_general_mode(monkeypatch):
    mode = AnswerModePlan(
        answer_mode="general",
        source_strategy="articles",
        response_shape="direct",
        streaming_allowed=True,
        rewrite_query=True,
        use_subquery_planner=False,
        default_prompt_case_id="innovasjon",
        answer_contract=GENERAL_DIRECT_CONTRACT,
    )
    monkeypatch.setattr(pipeline, "plan_query", lambda *_args, **_kwargs: _plan(mode))

    captured = {}

    def _fake_run_planned_single_pass(**kwargs):
        captured.update(kwargs)
        return ChatResponse(answer="ok", citations=[], retrieval_debug={"query_plan": {"answer_mode": "general"}})

    monkeypatch.setattr(pipeline, "_run_planned_single_pass", _fake_run_planned_single_pass)

    pipeline.answer_question("Hva sier litteraturen om innovasjonspolitikk?")

    assert captured["answer_contract"] == GENERAL_DIRECT_CONTRACT
