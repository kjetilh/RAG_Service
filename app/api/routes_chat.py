from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import text

from app.models.schemas import ChatRequest, ChatResponse, QueryRequest, QueryResponse
from app.rag.cases.loader import case_by_id, load_rag_cases
from app.rag.cases.visibility import visible_case_ids, visible_cases
from app.rag.generate.llm_provider import ModelProfileError, validate_model_profile
from app.rag.index.db import engine
from app.rag.pipeline import answer_question, answer_question_stream
from app.settings import settings

router = APIRouter()


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _resolve_download_path(stored_file_path: str) -> Path:
    root = Path(settings.ingest_root).expanduser().resolve(strict=False)
    requested = Path(stored_file_path).expanduser()
    candidate = requested.resolve(strict=False) if requested.is_absolute() else (root / requested).resolve(strict=False)

    if not _is_within(candidate, root):
        raise HTTPException(status_code=404, detail="Source file not found.")

    if candidate.is_file():
        return candidate

    rel = candidate.relative_to(root)
    done_candidate = (root / "done" / rel).resolve(strict=False)
    if _is_within(done_candidate, root) and done_candidate.is_file():
        return done_candidate

    failed_candidate = (root / "failed" / rel).resolve(strict=False)
    if _is_within(failed_candidate, root) and failed_candidate.is_file():
        return failed_candidate

    raise HTTPException(status_code=404, detail="Source file not found.")


def _document_file_path(doc_id: str) -> str:
    sql = "SELECT file_path FROM documents WHERE doc_id = :doc_id"
    with engine().begin() as conn:
        row = conn.execute(text(sql), {"doc_id": doc_id}).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    file_path = row[0]
    if not file_path:
        raise HTTPException(status_code=404, detail="No file registered for this document.")
    return str(file_path)


def _available_source_types() -> set[str]:
    sql = "SELECT DISTINCT source_type FROM documents WHERE source_type IS NOT NULL AND source_type <> ''"
    try:
        with engine().begin() as conn:
            rows = conn.execute(text(sql)).fetchall()
    except Exception:
        return set()
    return {str(row[0]).strip() for row in rows if row and str(row[0]).strip()}


def _filters_with_case(filters: dict | None, case_id: str | None) -> dict:
    out = dict(filters or {})
    if case_id:
        out["rag_case_id"] = case_id
    return out


def _run_query(req: QueryRequest):
    validate_model_profile(req.model_profile)
    cfg = load_rag_cases(settings.rag_cases_path)
    visible_ids = visible_case_ids(cfg)
    if req.case_id:
        if req.case_id not in visible_ids:
            raise HTTPException(status_code=404, detail=f"Case is not available on this instance: {req.case_id}")
        case_by_id(cfg, req.case_id)
    if req.prompt_profile_case_id:
        if req.prompt_profile_case_id not in visible_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Prompt profile case is not available on this instance: {req.prompt_profile_case_id}",
            )
        case_by_id(cfg, req.prompt_profile_case_id)
    return answer_question(
        message=req.query,
        conversation_id=req.conversation_id,
        filters=_filters_with_case(req.filters, req.case_id),
        top_k=req.top_k,
        model_profile=req.model_profile,
        prompt_profile_case_id=req.prompt_profile_case_id,
    )


@router.get("/v1/cases")
def list_cases():
    cfg = load_rag_cases(settings.rag_cases_path)
    available_source_types = _available_source_types()
    return {
        "cases": [
            {
                "case_id": case.case_id,
                "description": case.description,
                "enabled": case.enabled,
            }
            for case in visible_cases(cfg, available_source_types=available_source_types)
        ]
    }


@router.post("/v1/query", response_model=QueryResponse)
def query(req: QueryRequest):
    try:
        resp = _run_query(req)
        trace = None
        if resp.retrieval_debug and isinstance(resp.retrieval_debug, dict):
            trace = resp.retrieval_debug.get("query_plan")
        return QueryResponse(
            answer=resp.answer,
            citations=resp.citations,
            retrieval_debug=resp.retrieval_debug,
            trace=trace,
        )
    except ModelProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        query_req = QueryRequest(
            query=req.message,
            conversation_id=req.conversation_id,
            case_id=req.case_id,
            filters=req.filters or {},
            top_k=req.top_k,
            model_profile=req.model_profile,
            prompt_profile_case_id=req.prompt_profile_case_id,
        )
        resp = _run_query(query_req)
        return ChatResponse(
            answer=resp.answer,
            citations=resp.citations,
            retrieval_debug=resp.retrieval_debug,
        )
    except ModelProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/v1/chat/stream")
def chat_stream(req: ChatRequest):
    """Server-Sent Events (SSE) streaming endpoint.
    Events:
      - query_plan: JSON query plan (sent first)
      - status: JSON status update for long-running structured answers
      - citations: JSON citations list (sent first)
      - delta: incremental answer text chunks
      - done: indicates completion
    """
    try:
        validate_model_profile(req.model_profile)
        gen = answer_question_stream(
            message=req.message,
            conversation_id=req.conversation_id,
            filters=_filters_with_case(req.filters, req.case_id),
            top_k=req.top_k,
            model_profile=req.model_profile,
            prompt_profile_case_id=req.prompt_profile_case_id,
        )
        return StreamingResponse(gen, media_type="text/event-stream")
    except ModelProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/documents/{doc_id}/download")
def download_document(doc_id: str):
    file_path = _document_file_path(doc_id)
    resolved = _resolve_download_path(file_path)
    return FileResponse(path=str(resolved), filename=resolved.name)
