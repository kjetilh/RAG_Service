from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.schemas import ChatRequest, ChatResponse
from app.rag.pipeline import answer_question, answer_question_stream

router = APIRouter()

@router.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        return answer_question(
            message=req.message,
            conversation_id=req.conversation_id,
            filters=req.filters or {},
            top_k=req.top_k,
        )
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
        gen = answer_question_stream(
            message=req.message,
            conversation_id=req.conversation_id,
            filters=req.filters or {},
            top_k=req.top_k,
        )
        return StreamingResponse(gen, media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
