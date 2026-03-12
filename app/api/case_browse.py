from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.rag.audit.coverage_report import resolve_existing_file
from app.rag.cases.loader import case_by_id, load_rag_cases
from app.rag.index.db import engine
from app.settings import settings

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\n]+)\)")


class CaseQuickAction(BaseModel):
    label: str
    description: str
    prompt: str


class CaseSummary(BaseModel):
    case_id: str
    description: str
    enabled: bool
    role: str | None = None
    intended_for: str | None = None
    use_when: str | None = None
    avoid_when: str | None = None
    preferred_alternative_case_id: str | None = None
    quick_actions: list[CaseQuickAction] = Field(default_factory=list)


class CasesResponse(BaseModel):
    cases: list[CaseSummary]


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
