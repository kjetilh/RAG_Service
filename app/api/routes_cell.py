from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import secrets
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.routes_chat import _run_query
from app.models.schemas import QueryRequest, QueryResponse
from app.rag.interviews.collective import (
    CollectiveSummaryResponse,
    InterviewQuestion,
    build_collective_summary,
    prepare_question_set,
)
from app.rag.access.control import (
    ROLE_ORDER,
    case_exists,
    case_list_for_user,
    delete_case_member,
    global_owner_user_ids,
    has_case_role,
    list_case_members,
    resolve_case_role,
    upsert_case_member,
)
from app.rag.audit.coverage_report import resolve_existing_file
from app.rag.cases.loader import case_by_id, load_rag_cases
from app.rag.cases.visibility import visible_case_ids
from app.rag.generate.llm_provider import ModelProfileError, validate_model_profile
from app.rag.index.db import engine
from app.settings import settings

router = APIRouter()

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\n]+)\)")


@dataclass(frozen=True)
class CellIdentity:
    user_id: str | None
    via_admin_api_key: bool = False


class CaseSummary(BaseModel):
    case_id: str
    description: str
    enabled: bool
    role: str | None = None
    intended_for: str | None = None
    use_when: str | None = None
    avoid_when: str | None = None
    preferred_alternative_case_id: str | None = None


class CasesResponse(BaseModel):
    cases: list[CaseSummary]


class CaseMemberView(BaseModel):
    user_id: str
    role: Literal["owner", "admin", "viewer"]
    assigned_by: str | None = None


class CaseMembersResponse(BaseModel):
    case_id: str
    members: list[CaseMemberView]


class UpdateCaseMemberRequest(BaseModel):
    role: Literal["owner", "admin", "viewer"]


class CorpusDocument(BaseModel):
    doc_id: str
    title: str
    source_type: str | None = None
    author: str | None = None
    year: int | None = None
    url: str | None = None
    language: str | None = None
    file_path: str | None = None
    doc_state: str
    doc_version: int
    updated_at: datetime | None = None
    chunk_count: int


class CorpusResponse(BaseModel):
    case_id: str
    total: int
    limit: int
    offset: int
    items: list[CorpusDocument]


class LinkEdge(BaseModel):
    source_doc_id: str
    target_type: Literal["internal", "external", "unresolved"]
    target_doc_id: str | None = None
    target_href: str
    label: str | None = None
    target_title: str | None = None


class LinkGraphResponse(BaseModel):
    case_id: str
    doc_count: int
    edge_count: int
    items: list[LinkEdge]


class CellCollectiveSummaryRequest(BaseModel):
    prompt_profile_case_id: str | None = None
    question_set_path: str | None = None
    question_set_id: str | None = None
    questions: list[InterviewQuestion] | None = None
    filters: dict[str, Any] | None = None
    top_k: int | None = None
    model_profile: str | None = None


def _resolve_identity(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_cell_gateway_secret: str | None = Header(default=None, alias="X-Cell-Gateway-Secret"),
    x_cell_user_id: str | None = Header(default=None, alias="X-Cell-User-Id"),
) -> CellIdentity:
    if settings.admin_api_key and x_api_key and secrets.compare_digest(x_api_key, settings.admin_api_key):
        uid = x_cell_user_id.strip() if x_cell_user_id else "admin-api"
        return CellIdentity(user_id=uid, via_admin_api_key=True)

    if not settings.cell_access_control_enabled:
        uid = x_cell_user_id.strip() if x_cell_user_id and x_cell_user_id.strip() else None
        return CellIdentity(user_id=uid, via_admin_api_key=False)

    if not settings.cell_gateway_shared_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cell access is enabled, but CELL_GATEWAY_SHARED_SECRET is not configured.",
        )
    if not x_cell_gateway_secret or not secrets.compare_digest(
        x_cell_gateway_secret, settings.cell_gateway_shared_secret
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid gateway secret.")
    if not x_cell_user_id or not x_cell_user_id.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing cell user id.")
    return CellIdentity(user_id=x_cell_user_id.strip(), via_admin_api_key=False)


def _require_known_case(case_id: str) -> None:
    if not case_exists(case_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown case: {case_id}")
    cfg = load_rag_cases(settings.rag_cases_path)
    if case_id not in visible_case_ids(cfg):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown case: {case_id}")


def _require_role(case_id: str, identity: CellIdentity, minimum_role: str) -> str:
    _require_known_case(case_id)
    if identity.via_admin_api_key:
        return "owner"

    if not settings.cell_access_control_enabled:
        return "owner"

    if not has_case_role(case_id, identity.user_id, minimum_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have required role '{minimum_role}' for case '{case_id}'.",
        )
    role = resolve_case_role(case_id, identity.user_id)
    return role or "viewer"


def _case_source_types(case_id: str) -> list[str]:
    cfg = load_rag_cases(settings.rag_cases_path)
    selected = case_by_id(cfg, case_id)
    out: list[str] = []
    seen: set[str] = set()
    for value in list(selected.planner.docs_source_types) + list(selected.planner.prompts_source_types):
        item = (value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _sql_case_type_filter(source_types: list[str], params: dict[str, Any], clauses: list[str]) -> None:
    if not source_types:
        return
    params["source_types"] = source_types
    clauses.append("d.source_type = ANY(:source_types)")


def _corpus_rows(case_id: str, q: str | None, include_tombstones: bool, limit: int, offset: int) -> tuple[int, list[dict]]:
    source_types = _case_source_types(case_id)
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    _sql_case_type_filter(source_types, params, clauses)

    if not include_tombstones:
        clauses.append("d.doc_state = 'active'")
    if q:
        params["q"] = f"%{q.strip().lower()}%"
        clauses.append("(LOWER(d.title) LIKE :q OR LOWER(d.doc_id) LIKE :q)")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    count_sql = f"""
    SELECT COUNT(*)
    FROM documents d
    {where_sql}
    """
    data_sql = f"""
    SELECT
      d.doc_id,
      d.title,
      d.source_type,
      d.author,
      d.year,
      d.url,
      d.language,
      d.file_path,
      d.doc_state,
      d.doc_version,
      d.updated_at,
      COALESCE(COUNT(c.chunk_id), 0) AS chunk_count
    FROM documents d
    LEFT JOIN chunks c ON c.doc_id = d.doc_id
    {where_sql}
    GROUP BY
      d.doc_id, d.title, d.source_type, d.author, d.year, d.url, d.language,
      d.file_path, d.doc_state, d.doc_version, d.updated_at
    ORDER BY d.source_type NULLS LAST, d.title, d.doc_id
    LIMIT :limit OFFSET :offset
    """
    with engine().begin() as conn:
        total = int(conn.execute(text(count_sql), params).scalar() or 0)
        rows = conn.execute(text(data_sql), params).mappings().all()
    return total, [dict(r) for r in rows]


def _extract_md_links(content: str) -> list[tuple[str | None, str]]:
    out: list[tuple[str | None, str]] = []
    for match in _MD_LINK_RE.finditer(content or ""):
        label = (match.group(1) or "").strip() or None
        target = (match.group(2) or "").strip()
        if not target:
            continue
        out.append((label, target))
    return out


def _strip_anchor_and_query(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    # keep path-only when markdown target is relative
    return parsed.path or ""


def _resolve_internal_target(
    source_file: Path,
    href: str,
    path_to_doc: dict[str, str],
    by_basename: dict[str, list[str]],
) -> str | None:
    raw_path = _strip_anchor_and_query(href)
    if not raw_path or raw_path.startswith("#"):
        return None

    if raw_path.startswith("/"):
        candidate = Path(raw_path).expanduser().resolve(strict=False)
    else:
        candidate = (source_file.parent / raw_path).resolve(strict=False)
    candidate_key = str(candidate)

    if candidate_key in path_to_doc:
        return path_to_doc[candidate_key]
    if candidate.suffix == "":
        md_candidate = str(candidate.with_suffix(".md"))
        if md_candidate in path_to_doc:
            return path_to_doc[md_candidate]

    basename = candidate.name.lower()
    matches = by_basename.get(basename, [])
    if len(matches) == 1:
        return matches[0]
    return None


def _link_docs_for_case(case_id: str, only_doc_id: str | None = None, limit_docs: int = 300) -> list[dict]:
    source_types = _case_source_types(case_id)
    clauses = ["d.doc_state = 'active'"]
    params: dict[str, Any] = {"limit_docs": max(1, limit_docs)}
    _sql_case_type_filter(source_types, params, clauses)
    if only_doc_id:
        clauses.append("d.doc_id = :doc_id")
        params["doc_id"] = only_doc_id
    where_sql = "WHERE " + " AND ".join(clauses)
    sql = f"""
    SELECT d.doc_id, d.title, d.file_path
    FROM documents d
    {where_sql}
    ORDER BY d.doc_id
    LIMIT :limit_docs
    """
    with engine().begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def _build_link_graph(case_id: str, only_doc_id: str | None = None, limit_docs: int = 300) -> LinkGraphResponse:
    docs = _link_docs_for_case(case_id, only_doc_id=only_doc_id, limit_docs=limit_docs)
    title_by_doc = {str(d["doc_id"]): str(d.get("title") or "") for d in docs}

    path_to_doc: dict[str, str] = {}
    by_basename: dict[str, list[str]] = defaultdict(list)
    resolved_file_by_doc: dict[str, Path] = {}
    for doc in docs:
        doc_id = str(doc["doc_id"])
        file_path = doc.get("file_path")
        if not file_path:
            continue
        resolved = resolve_existing_file(str(file_path), ingest_root=settings.ingest_root)
        if resolved is None:
            continue
        key = str(resolved.resolve(strict=False))
        path_to_doc[key] = doc_id
        by_basename[resolved.name.lower()].append(doc_id)
        resolved_file_by_doc[doc_id] = resolved

    seen_edges: set[tuple[str, str, str, str | None, str | None]] = set()
    edges: list[LinkEdge] = []

    for source_doc_id in sorted(resolved_file_by_doc.keys()):
        source_file = resolved_file_by_doc[source_doc_id]
        try:
            content = source_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for label, href in _extract_md_links(content):
            parsed = urlparse(href)
            if parsed.scheme in {"http", "https", "mailto", "tel"}:
                key = (source_doc_id, "external", href, label, None)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append(
                    LinkEdge(
                        source_doc_id=source_doc_id,
                        target_type="external",
                        target_href=href,
                        label=label,
                    )
                )
                continue

            target_doc_id = _resolve_internal_target(source_file, href, path_to_doc, by_basename)
            if target_doc_id:
                key = (source_doc_id, "internal", target_doc_id, label, href)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append(
                    LinkEdge(
                        source_doc_id=source_doc_id,
                        target_type="internal",
                        target_doc_id=target_doc_id,
                        target_href=href,
                        label=label,
                        target_title=title_by_doc.get(target_doc_id),
                    )
                )
                continue

            key = (source_doc_id, "unresolved", href, label, None)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append(
                LinkEdge(
                    source_doc_id=source_doc_id,
                    target_type="unresolved",
                    target_href=href,
                    label=label,
                )
            )

    items = sorted(
        edges,
        key=lambda x: (
            x.source_doc_id,
            x.target_type,
            x.target_doc_id or "",
            x.target_href,
            x.label or "",
        ),
    )
    return LinkGraphResponse(case_id=case_id, doc_count=len(docs), edge_count=len(items), items=items)


@router.get("/v1/cell/cases", response_model=CasesResponse)
def cell_cases(identity: CellIdentity = Depends(_resolve_identity)):
    rows = case_list_for_user(identity.user_id)
    if settings.cell_access_control_enabled and not identity.via_admin_api_key:
        rows = [r for r in rows if r.get("role")]
    cases = [CaseSummary(**r) for r in rows]
    return CasesResponse(cases=cases)


@router.post("/v1/cell/cases/{case_id}/query", response_model=QueryResponse)
def cell_query(case_id: str, req: QueryRequest, identity: CellIdentity = Depends(_resolve_identity)):
    _require_role(case_id, identity, "viewer")
    query_req = QueryRequest(
        query=req.query,
        conversation_id=req.conversation_id,
        case_id=case_id,
        filters=req.filters or {},
        top_k=req.top_k,
        model_profile=req.model_profile,
        prompt_profile_case_id=req.prompt_profile_case_id,
    )
    try:
        resp = _run_query(query_req)
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/v1/cell/cases/{case_id}/interviews/collective-summary", response_model=CollectiveSummaryResponse)
def cell_collective_summary(
    case_id: str,
    req: CellCollectiveSummaryRequest,
    identity: CellIdentity = Depends(_resolve_identity),
):
    _require_role(case_id, identity, "viewer")
    try:
        validate_model_profile(req.model_profile)
        question_set = prepare_question_set(
            inline_questions=req.questions,
            question_set_path=req.question_set_path,
            question_set_id=req.question_set_id,
        )
        return build_collective_summary(
            case_id=case_id,
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


@router.get("/v1/cell/cases/{case_id}/corpus", response_model=CorpusResponse)
def cell_corpus(
    case_id: str,
    identity: CellIdentity = Depends(_resolve_identity),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    include_tombstones: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    _require_role(case_id, identity, "viewer")
    total, rows = _corpus_rows(case_id, q, include_tombstones, limit, offset)
    items = [CorpusDocument(**row) for row in rows]
    return CorpusResponse(case_id=case_id, total=total, limit=limit, offset=offset, items=items)


@router.get("/v1/cell/cases/{case_id}/links", response_model=LinkGraphResponse)
def cell_case_links(
    case_id: str,
    identity: CellIdentity = Depends(_resolve_identity),
    limit_docs: int = Query(default=300, ge=1, le=2000),
):
    _require_role(case_id, identity, "viewer")
    return _build_link_graph(case_id, only_doc_id=None, limit_docs=limit_docs)


@router.get("/v1/cell/cases/{case_id}/documents/{doc_id}/links", response_model=LinkGraphResponse)
def cell_document_links(
    case_id: str,
    doc_id: str,
    identity: CellIdentity = Depends(_resolve_identity),
):
    _require_role(case_id, identity, "viewer")
    return _build_link_graph(case_id, only_doc_id=doc_id, limit_docs=1)


def _actor_role(case_id: str, identity: CellIdentity) -> str:
    if identity.via_admin_api_key:
        return "owner"
    if not settings.cell_access_control_enabled:
        return "owner"
    role = resolve_case_role(case_id, identity.user_id)
    return role or "viewer"


@router.get("/v1/cell/cases/{case_id}/members", response_model=CaseMembersResponse)
def cell_case_members(case_id: str, identity: CellIdentity = Depends(_resolve_identity)):
    _require_role(case_id, identity, "admin")
    members = [
        CaseMemberView(user_id=m.user_id, role=m.role, assigned_by=m.assigned_by)
        for m in list_case_members(case_id)
    ]
    return CaseMembersResponse(case_id=case_id, members=members)


@router.put("/v1/cell/cases/{case_id}/members/{target_user_id}", response_model=CaseMembersResponse)
def cell_case_member_upsert(
    case_id: str,
    target_user_id: str,
    req: UpdateCaseMemberRequest,
    identity: CellIdentity = Depends(_resolve_identity),
):
    _require_known_case(case_id)
    actor_role = _actor_role(case_id, identity)
    if not identity.via_admin_api_key and ROLE_ORDER.get(actor_role, 0) < ROLE_ORDER["owner"]:
        raise HTTPException(status_code=403, detail="Only case owner can assign members.")
    if req.role == "owner" and not identity.via_admin_api_key:
        raise HTTPException(status_code=403, detail="Only admin API key can grant owner role.")

    if (target_user_id or "").strip() in global_owner_user_ids() and req.role != "owner":
        raise HTTPException(status_code=400, detail="Cannot downgrade env-defined owner.")

    upsert_case_member(
        case_id=case_id,
        user_id=target_user_id,
        role=req.role,
        assigned_by=identity.user_id,
    )
    members = [
        CaseMemberView(user_id=m.user_id, role=m.role, assigned_by=m.assigned_by)
        for m in list_case_members(case_id)
    ]
    return CaseMembersResponse(case_id=case_id, members=members)


@router.delete("/v1/cell/cases/{case_id}/members/{target_user_id}", response_model=CaseMembersResponse)
def cell_case_member_delete(
    case_id: str,
    target_user_id: str,
    identity: CellIdentity = Depends(_resolve_identity),
):
    _require_known_case(case_id)
    actor_role = _actor_role(case_id, identity)
    if not identity.via_admin_api_key and ROLE_ORDER.get(actor_role, 0) < ROLE_ORDER["owner"]:
        raise HTTPException(status_code=403, detail="Only case owner can remove members.")

    normalized_target = (target_user_id or "").strip()
    if normalized_target in global_owner_user_ids() and not identity.via_admin_api_key:
        raise HTTPException(status_code=400, detail="Cannot remove env-defined owner.")

    target_role = resolve_case_role(case_id, normalized_target)
    if target_role == "owner" and not identity.via_admin_api_key:
        raise HTTPException(status_code=403, detail="Only admin API key can remove owner role.")

    delete_case_member(case_id=case_id, user_id=normalized_target)
    members = [
        CaseMemberView(user_id=m.user_id, role=m.role, assigned_by=m.assigned_by)
        for m in list_case_members(case_id)
    ]
    return CaseMembersResponse(case_id=case_id, members=members)
