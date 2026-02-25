from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import text

from app.models.schemas import ChatRequest, ChatResponse
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

@router.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        validate_model_profile(req.model_profile)
        return answer_question(
            message=req.message,
            conversation_id=req.conversation_id,
            filters=req.filters or {},
            top_k=req.top_k,
            model_profile=req.model_profile,
        )
    except ModelProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/v1/chat/stream")
def chat_stream(req: ChatRequest):
    """Server-Sent Events (SSE) streaming endpoint.
    Events:
      - citations: JSON citations list (sent first)
      - delta: incremental answer text chunks
      - done: indicates completion
    """
    try:
        validate_model_profile(req.model_profile)
        gen = answer_question_stream(
            message=req.message,
            conversation_id=req.conversation_id,
            filters=req.filters or {},
            top_k=req.top_k,
            model_profile=req.model_profile,
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
