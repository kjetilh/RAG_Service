from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.schemas import Citation, QueryRequest


DEFAULT_QUESTION_SET_PATH = "config/interview_questions.example.yml"


class InterviewQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4000)


class InterviewQuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    question_set_id: str = Field(min_length=1, max_length=120)
    language: str | None = None
    questions: list[InterviewQuestion] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _validate_unique_question_ids(self):
        ids = [q.question_id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate question_id in question set.")
        return self


class PreparedQuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_set_id: str
    questions: list[InterviewQuestion]
    source: Literal["inline", "file"]
    source_path: str | None = None


class CollectiveSummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    status: Literal["ok", "error"]
    answer: str | None = None
    citation_count: int = 0
    unique_doc_count: int = 0
    citations: list[Citation] = Field(default_factory=list)
    trace: dict[str, Any] | None = None
    retrieval_debug: dict[str, Any] | None = None
    error: str | None = None


class CollectiveSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str | None = None
    question_set_id: str
    question_count: int
    succeeded_count: int
    failed_count: int
    items: list[CollectiveSummaryItem]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_question_set_path(raw_path: str) -> Path:
    repo_root = _repo_root()
    requested = Path(raw_path).expanduser()
    if requested.is_absolute():
        candidate = requested.resolve(strict=False)
    else:
        candidate = (repo_root / requested).resolve(strict=False)

    if candidate != repo_root and repo_root not in candidate.parents:
        raise ValueError(f"question_set_path must be inside repository root: {repo_root}")
    if not candidate.is_file():
        raise ValueError(f"Question set file not found: {candidate}")
    return candidate


def _load_question_set_from_file(path: str) -> PreparedQuestionSet:
    resolved = _resolve_question_set_path(path)
    parsed = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if parsed is None:
        raise ValueError(f"Question set file is empty: {resolved}")
    if not isinstance(parsed, dict):
        raise ValueError("Question set root must be a mapping.")
    cfg = InterviewQuestionSet.model_validate(parsed)
    return PreparedQuestionSet(
        question_set_id=cfg.question_set_id,
        questions=list(cfg.questions),
        source="file",
        source_path=str(resolved),
    )


def prepare_question_set(
    *,
    inline_questions: list[InterviewQuestion] | list[dict[str, Any]] | None,
    question_set_path: str | None,
    question_set_id: str | None = None,
    default_question_set_path: str = DEFAULT_QUESTION_SET_PATH,
) -> PreparedQuestionSet:
    if inline_questions:
        questions = [InterviewQuestion.model_validate(q) for q in inline_questions]
        ids = [q.question_id for q in questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate question_id in inline questions.")
        return PreparedQuestionSet(
            question_set_id=(question_set_id or "inline-question-set").strip(),
            questions=questions,
            source="inline",
            source_path=None,
        )

    effective_path = (question_set_path or "").strip() or default_question_set_path
    loaded = _load_question_set_from_file(effective_path)
    if question_set_id and question_set_id.strip():
        loaded.question_set_id = question_set_id.strip()
    return loaded


def _extract_trace_and_debug(response: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    retrieval_debug = getattr(response, "retrieval_debug", None)
    trace = getattr(response, "trace", None)
    if trace is None and isinstance(retrieval_debug, dict):
        trace = retrieval_debug.get("query_plan")
    return trace, retrieval_debug if isinstance(retrieval_debug, dict) else None


def build_collective_summary(
    *,
    case_id: str | None,
    question_set: PreparedQuestionSet,
    filters: dict[str, Any] | None,
    top_k: int | None,
    model_profile: str | None,
    run_query_fn: Callable[[QueryRequest], Any],
) -> CollectiveSummaryResponse:
    base_filters = dict(filters or {})
    items: list[CollectiveSummaryItem] = []

    for question in question_set.questions:
        req = QueryRequest(
            query=question.text,
            case_id=case_id,
            filters=dict(base_filters),
            top_k=top_k,
            model_profile=model_profile,
        )
        try:
            result = run_query_fn(req)
            citations = list(getattr(result, "citations", []) or [])
            trace, retrieval_debug = _extract_trace_and_debug(result)
            unique_docs = len({c.doc_id for c in citations if getattr(c, "doc_id", None)})
            items.append(
                CollectiveSummaryItem(
                    question_id=question.question_id,
                    question=question.text,
                    status="ok",
                    answer=getattr(result, "answer", "") or "",
                    citation_count=len(citations),
                    unique_doc_count=unique_docs,
                    citations=citations,
                    trace=trace,
                    retrieval_debug=retrieval_debug,
                    error=None,
                )
            )
        except Exception as e:
            items.append(
                CollectiveSummaryItem(
                    question_id=question.question_id,
                    question=question.text,
                    status="error",
                    answer=None,
                    citation_count=0,
                    unique_doc_count=0,
                    citations=[],
                    trace=None,
                    retrieval_debug=None,
                    error=str(e),
                )
            )

    succeeded_count = sum(1 for item in items if item.status == "ok")
    failed_count = len(items) - succeeded_count
    return CollectiveSummaryResponse(
        case_id=case_id,
        question_set_id=question_set.question_set_id,
        question_count=len(question_set.questions),
        succeeded_count=succeeded_count,
        failed_count=failed_count,
        items=items,
    )
