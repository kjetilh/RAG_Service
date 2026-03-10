from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    case_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    filters: Optional[Dict[str, Any]] = None
    top_k: Optional[int] = None
    model_profile: Optional[str] = Field(default=None, min_length=1, max_length=64)
    prompt_profile_case_id: Optional[str] = Field(default=None, min_length=1, max_length=80)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    case_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    filters: Optional[Dict[str, Any]] = None
    top_k: Optional[int] = None
    model_profile: Optional[str] = Field(default=None, min_length=1, max_length=64)
    prompt_profile_case_id: Optional[str] = Field(default=None, min_length=1, max_length=80)

class Citation(BaseModel):
    doc_id: str
    title: str
    chunk_id: str
    score: float
    excerpt: str
    download_url: Optional[str] = None
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


class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
    retrieval_debug: Optional[Dict[str, Any]] = None
    trace: Optional[Dict[str, Any]] = None
