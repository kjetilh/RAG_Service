from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    top_k: Optional[int] = None

class Citation(BaseModel):
    doc_id: str
    title: str
    chunk_id: str
    score: float
    excerpt: str
    year: Optional[int] = None
    author: Optional[str] = None
    source_type: Optional[str] = None
    publisher: Optional[str] = None
    url: Optional[str] = None
    language: Optional[str] = None
    identifiers: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation]
    retrieval_debug: Optional[Dict[str, Any]] = None
