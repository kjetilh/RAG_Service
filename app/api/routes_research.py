from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import time
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.routes_cell import (
    CaseSummary,
    CasesResponse,
    CorpusResponse,
    LinkGraphResponse,
    _build_link_graph,
    _case_source_types,
    _corpus_rows,
)
from app.api.routes_chat import _document_file_path, _resolve_download_path, _run_query
from app.models.schemas import Citation, QueryRequest, QueryResponse
from app.rag.access.control import case_exists
from app.rag.cases.loader import load_rag_cases
from app.rag.cases.visibility import visible_case_ids
from app.rag.generate.llm_provider import ModelProfileError
from app.rag.index.db import engine
from app.settings import settings

router = APIRouter()


@dataclass(frozen=True)
class ResearchIdentity:
    token: str
    label: str | None
    scopes: frozenset[str]
    case_ids: frozenset[str] | None = None


class ResearchTokenPolicy(BaseModel):
    label: str | None = None
    scopes: list[str] = Field(default_factory=lambda: ["research:read"])
    case_ids: list[str] = Field(default_factory=list)


class ResearchQueryRequest(BaseModel):
    case_id: str = Field(..., min_length=1, max_length=80)
    query: str = Field(..., min_length=1)
    conversation_id: str | None = None
    filters: dict[str, Any] | None = None
    top_k: int | None = None
    model_profile: str | None = Field(default=None, min_length=1, max_length=64)
    prompt_profile_case_id: str | None = Field(default=None, min_length=1, max_length=80)


class SignedDownloadGrant(BaseModel):
    expires_at: int = Field(..., alias="exp")
    signature: str = Field(..., alias="sig", min_length=1)
    case_scope: str = Field(..., alias="cases", min_length=1)


def _parse_research_token_policies() -> dict[str, ResearchTokenPolicy]:
    raw = (settings.research_api_tokens_json or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception as exc:  # pragma: no cover - exercised through dependency error handling
        raise ValueError(f"RESEARCH_API_TOKENS_JSON is invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("RESEARCH_API_TOKENS_JSON must be a JSON object mapping token -> policy.")

    policies: dict[str, ResearchTokenPolicy] = {}
    for token, payload in parsed.items():
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Research token keys must be non-empty strings.")
        policies[token.strip()] = ResearchTokenPolicy.model_validate(payload or {})
    return policies


def _extract_presented_token(authorization: str | None, access_token: str | None) -> str:
    header_token: str | None = None
    if authorization:
        scheme, _, value = authorization.strip().partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token.")
        header_token = value.strip()

    query_token = (access_token or "").strip() or None
    if header_token and query_token and not secrets.compare_digest(header_token, query_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization bearer token and access_token query parameter did not match.",
        )

    token = header_token or query_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing research access token.")
    return token


def _resolve_research_identity(
    authorization: str | None = Header(default=None, alias="Authorization"),
    access_token: str | None = Query(default=None),
) -> ResearchIdentity:
    try:
        policies = _parse_research_token_policies()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    if not policies:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Research API is not configured. Set RESEARCH_API_TOKENS_JSON.",
        )

    presented = _extract_presented_token(authorization=authorization, access_token=access_token)
    for configured_token, policy in policies.items():
        if not secrets.compare_digest(configured_token, presented):
            continue
        normalized_scopes = frozenset(
            scope.strip() for scope in policy.scopes if isinstance(scope, str) and scope.strip()
        ) or frozenset({"research:read"})
        normalized_cases = frozenset(
            case_id.strip() for case_id in policy.case_ids if isinstance(case_id, str) and case_id.strip()
        )
        return ResearchIdentity(
            token=presented,
            label=(policy.label.strip() if isinstance(policy.label, str) and policy.label.strip() else None),
            scopes=normalized_scopes,
            case_ids=(normalized_cases or None),
        )

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid research access token.")


def _has_scope(identity: ResearchIdentity, required_scope: str) -> bool:
    scopes = identity.scopes
    return required_scope in scopes or "research:*" in scopes or "*" in scopes


def _require_scope(identity: ResearchIdentity, required_scope: str) -> None:
    if _has_scope(identity, required_scope):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Research token is missing required scope '{required_scope}'.",
    )


def _allowed_case_ids(identity: ResearchIdentity) -> set[str]:
    cfg = load_rag_cases(settings.rag_cases_path)
    enabled = visible_case_ids(cfg)
    if identity.case_ids is None:
        return enabled
    return enabled.intersection(identity.case_ids)


def _optional_research_identity(
    authorization: str | None = Header(default=None, alias="Authorization"),
    access_token: str | None = Query(default=None),
) -> ResearchIdentity | None:
    if not authorization and not access_token:
        return None
    return _resolve_research_identity(authorization=authorization, access_token=access_token)


def _require_case_access(case_id: str, identity: ResearchIdentity) -> None:
    if not case_exists(case_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown case: {case_id}")
    if case_id not in _allowed_case_ids(identity):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown case: {case_id}",
        )


def _citation_payload(citation: Citation) -> dict[str, Any]:
    if hasattr(citation, "model_dump"):
        return citation.model_dump()
    return citation.dict()


def _signing_key() -> bytes | None:
    key = (settings.research_download_signing_key or "").strip()
    return key.encode("utf-8") if key else None


def _case_scope_string(case_ids: set[str]) -> str:
    normalized = sorted(case_id.strip() for case_id in case_ids if case_id and case_id.strip())
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Research token is not allowed to access any enabled cases.",
        )
    return ",".join(normalized)


def _download_signature(doc_id: str, expires_at: int, case_scope: str) -> str:
    key = _signing_key()
    if key is None:
        raise RuntimeError("Research download signing key is not configured.")
    payload = "\n".join([doc_id, str(expires_at), case_scope]).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _signed_download_grant(doc_id: str, identity: ResearchIdentity) -> SignedDownloadGrant:
    case_scope = _case_scope_string(_allowed_case_ids(identity))
    expires_at = int(time.time()) + max(1, int(settings.research_download_ttl_seconds))
    return SignedDownloadGrant(
        exp=expires_at,
        sig=_download_signature(doc_id, expires_at, case_scope),
        cases=case_scope,
    )


def _signed_download_url(doc_id: str, identity: ResearchIdentity) -> str:
    grant = _signed_download_grant(doc_id, identity)
    escaped_doc_id = quote(doc_id, safe="")
    escaped_cases = quote(grant.case_scope, safe="")
    escaped_sig = quote(grant.signature, safe="")
    return f"/v1/research/documents/{escaped_doc_id}/download?exp={grant.expires_at}&cases={escaped_cases}&sig={escaped_sig}"


def _legacy_research_download_url(doc_id: str, identity: ResearchIdentity) -> str | None:
    if not _has_scope(identity, "research:download"):
        return None
    escaped_doc_id = quote(doc_id, safe="")
    escaped_token = quote(identity.token, safe="")
    return f"/v1/research/documents/{escaped_doc_id}/download?access_token={escaped_token}"


def _research_download_url(doc_id: str, identity: ResearchIdentity) -> str | None:
    if not _has_scope(identity, "research:download"):
        return None
    if _signing_key() is None:
        return _legacy_research_download_url(doc_id, identity)
    return _signed_download_url(doc_id, identity)


def _rewrite_query_response_for_research(response: QueryResponse, identity: ResearchIdentity) -> QueryResponse:
    rewritten_citations = [
        Citation(
            **{
                **_citation_payload(citation),
                "download_url": _research_download_url(citation.doc_id, identity),
            }
        )
        for citation in response.citations
    ]
    trace = None
    if response.retrieval_debug and isinstance(response.retrieval_debug, dict):
        trace = response.retrieval_debug.get("query_plan")
    return QueryResponse(
        answer=response.answer,
        citations=rewritten_citations,
        retrieval_debug=response.retrieval_debug,
        trace=trace,
    )


def _document_case_ids(doc_id: str) -> set[str]:
    sql = """
    SELECT source_type, doc_state
    FROM documents
    WHERE doc_id = :doc_id
    LIMIT 1
    """
    with engine().begin() as conn:
        row = conn.execute(text(sql), {"doc_id": doc_id}).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    source_type = str(row[0] or "").strip()
    doc_state = str(row[1] or "").strip()
    if doc_state and doc_state != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document is not active.")
    if not source_type:
        return set()

    cfg = load_rag_cases(settings.rag_cases_path)
    matches: set[str] = set()
    for case in cfg.cases:
        if not case.enabled:
            continue
        if source_type in _case_source_types(case.case_id):
            matches.add(case.case_id)
    return matches


def _require_document_access(doc_id: str, identity: ResearchIdentity) -> None:
    doc_cases = _document_case_ids(doc_id)
    if not doc_cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document is not mapped to an enabled research case.",
        )
    if not doc_cases.intersection(_allowed_case_ids(identity)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )


def _parse_signed_case_scope(case_scope: str) -> set[str]:
    return {value.strip() for value in case_scope.split(",") if value.strip()}


def _require_signed_download_access(doc_id: str, grant: SignedDownloadGrant) -> None:
    if _signing_key() is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signed research downloads are not configured.",
        )
    if grant.expires_at < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Research download link has expired.")

    case_ids = _parse_signed_case_scope(grant.case_scope)
    if not case_ids:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Research download link is invalid.")

    expected = _download_signature(doc_id, grant.expires_at, grant.case_scope)
    if not secrets.compare_digest(expected, grant.signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Research download link is invalid.")

    doc_cases = _document_case_ids(doc_id)
    if not doc_cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document is not mapped to an enabled research case.",
        )
    if not doc_cases.intersection(case_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )


@router.get("/v1/research/cases", response_model=CasesResponse)
def research_cases(identity: ResearchIdentity = Depends(_resolve_research_identity)):
    _require_scope(identity, "research:read")
    cfg = load_rag_cases(settings.rag_cases_path)
    allowed_case_ids = _allowed_case_ids(identity)
    items = [
        CaseSummary(case_id=case.case_id, description=case.description, enabled=bool(case.enabled), role=None)
        for case in cfg.cases
        if case.enabled and case.case_id in allowed_case_ids
    ]
    return CasesResponse(cases=items)


@router.post("/v1/research/query", response_model=QueryResponse)
def research_query(req: ResearchQueryRequest, identity: ResearchIdentity = Depends(_resolve_research_identity)):
    _require_scope(identity, "research:read")
    _require_case_access(req.case_id, identity)
    query_req = QueryRequest(
        query=req.query,
        conversation_id=req.conversation_id,
        case_id=req.case_id,
        filters=req.filters or {},
        top_k=req.top_k,
        model_profile=req.model_profile,
        prompt_profile_case_id=req.prompt_profile_case_id,
    )
    try:
        response = _run_query(query_req)
        return _rewrite_query_response_for_research(response, identity)
    except ModelProfileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/v1/research/cases/{case_id}/corpus", response_model=CorpusResponse)
def research_corpus(
    case_id: str,
    identity: ResearchIdentity = Depends(_resolve_research_identity),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    include_tombstones: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    _require_scope(identity, "research:read")
    _require_case_access(case_id, identity)
    total, rows = _corpus_rows(case_id, q, include_tombstones, limit, offset)
    return CorpusResponse(case_id=case_id, total=total, limit=limit, offset=offset, items=rows)


@router.get("/v1/research/cases/{case_id}/links", response_model=LinkGraphResponse)
def research_case_links(
    case_id: str,
    identity: ResearchIdentity = Depends(_resolve_research_identity),
    limit_docs: int = Query(default=300, ge=1, le=2000),
):
    _require_scope(identity, "research:read")
    _require_case_access(case_id, identity)
    return _build_link_graph(case_id, only_doc_id=None, limit_docs=limit_docs)


@router.get("/v1/research/cases/{case_id}/documents/{doc_id}/links", response_model=LinkGraphResponse)
def research_document_links(
    case_id: str,
    doc_id: str,
    identity: ResearchIdentity = Depends(_resolve_research_identity),
):
    _require_scope(identity, "research:read")
    _require_case_access(case_id, identity)
    return _build_link_graph(case_id, only_doc_id=doc_id, limit_docs=1)


@router.get("/v1/research/documents/{doc_id}/download")
def research_download_document(
    doc_id: str,
    exp: int | None = Query(default=None),
    sig: str | None = Query(default=None),
    cases: str | None = Query(default=None),
    identity: ResearchIdentity | None = Depends(_optional_research_identity),
):
    if identity is not None:
        _require_scope(identity, "research:download")
        _require_document_access(doc_id, identity)
    else:
        if exp is None or sig is None or cases is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing research access token or signed download grant.",
            )
        _require_signed_download_access(doc_id, SignedDownloadGrant(exp=exp, sig=sig, cases=cases))
    file_path = _document_file_path(doc_id)
    resolved = _resolve_download_path(file_path)
    return FileResponse(path=str(resolved), filename=Path(resolved).name)
