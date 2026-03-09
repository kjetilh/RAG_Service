from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.routes_chat import _run_query
from app.rag.generate.llm_provider import ModelProfileError, validate_model_profile
from app.rag.interviews.collective import (
    CollectiveSummaryResponse,
    InterviewQuestion,
    build_collective_summary,
    prepare_question_set,
)

router = APIRouter()


class CollectiveSummaryRequest(BaseModel):
    case_id: str | None = Field(default=None, min_length=1, max_length=80)
    prompt_profile_case_id: str | None = Field(default=None, min_length=1, max_length=80)
    question_set_path: str | None = Field(default=None, min_length=1, max_length=260)
    question_set_id: str | None = Field(default=None, min_length=1, max_length=120)
    questions: list[InterviewQuestion] | None = None
    filters: dict[str, Any] | None = None
    top_k: int | None = Field(default=None, ge=1, le=200)
    model_profile: str | None = Field(default=None, min_length=1, max_length=64)


@router.post("/v1/interviews/collective-summary", response_model=CollectiveSummaryResponse)
def interviews_collective_summary(req: CollectiveSummaryRequest):
    try:
        validate_model_profile(req.model_profile)
        question_set = prepare_question_set(
            inline_questions=req.questions,
            question_set_path=req.question_set_path,
            question_set_id=req.question_set_id,
        )
        return build_collective_summary(
            case_id=req.case_id,
            prompt_profile_case_id=req.prompt_profile_case_id,
            question_set=question_set,
            filters=req.filters,
            top_k=req.top_k,
            model_profile=req.model_profile,
            run_query_fn=_run_query,
        )
    except ModelProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
