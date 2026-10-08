"""Document link graph, used to add linked documents to a retrieval result.

The graph is built from the documentation itself: markdown links, [[wikilinks]]
and mentions of another document's file name. Shared identifiers are NOT edges:
measured 2026-10-08, a symbol co-occurrence graph and a PageRank-style ranking
both lowered precision (document-hit@5 fell 4-7 points).

What the graph is used for is narrow on purpose ("reserved slots"): the fused
ranking is left untouched, and the best chunk of documents linked from the top
documents takes the last places of the context. A question that needs two
documents then gets the second one even when it does not resemble the question.
"""
from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

import numpy as np
from sqlalchemy import text

from app.rag.index.db import engine
from app.settings import settings

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s#]+)(?:#[^)]*)?\)")
_WIKI_RE = re.compile(r"\[\[([^\]|#]+)")
_PATHISH_RE = re.compile(r"[\w./-]+\.(?:md|json|swift|py|sh)")
_URL_RE = re.compile(r"https?://\S+")


def build_link_graph(docs: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """docs: [{"doc_id", "file_path", "text"}] -> adjacency {doc_id: {doc_id: weight}}."""
    by_path: dict[str, str] = {}
    by_name: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        path = str(d.get("file_path") or "")
        if not path:
            continue
        by_path[os.path.normpath(path)] = d["doc_id"]
        pp = PurePosixPath(path)
        by_name[pp.name.lower()].append(d["doc_id"])
        by_name[pp.stem.lower()].append(d["doc_id"])
    adj: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def add(a: str, b: str, weight: float) -> None:
        if a != b:
            adj[a][b] += weight
            adj[b][a] += weight * 0.7

    def unique(name: str) -> str | None:
        candidates = by_name.get(name.lower(), [])
        return candidates[0] if len(set(candidates)) == 1 else None

    for d in docs:
        source = d["doc_id"]
        base = PurePosixPath(str(d.get("file_path") or "")).parent
        body = d.get("text") or ""
        for m in _LINK_RE.finditer(body):
            href = m.group(1)
            if "://" in href or href.startswith("mailto:"):
                continue
            target = by_path.get(os.path.normpath(str(base / href))) or unique(PurePosixPath(href).name)
            if target:
                add(source, target, 1.0)
        for m in _WIKI_RE.finditer(body):
            target = unique(m.group(1).strip())
            if target:
                add(source, target, 1.0)
        for m in _PATHISH_RE.finditer(_URL_RE.sub(" ", body)):
            target = unique(PurePosixPath(m.group(0)).name)
            if target:
                add(source, target, 0.6)
    return {k: dict(v) for k, v in adj.items()}


_lock = threading.Lock()
_graph: dict[str, dict[str, float]] | None = None
_signature: tuple | None = None
_checked_at = 0.0
CHECK_INTERVAL_SECONDS = 60.0


def _db_signature() -> tuple:
    sql = """
    SELECT (SELECT count(*) FROM chunks),
           (SELECT count(*) FROM documents WHERE COALESCE(doc_state, 'active') = 'active'),
           (SELECT COALESCE(max(updated_at)::text, '') FROM documents)
    """
    with engine().begin() as conn:
        return tuple(conn.execute(text(sql)).fetchone())


def _load_docs() -> list[dict[str, Any]]:
    sql = """
    SELECT d.doc_id, d.file_path, string_agg(c.content, E'\\n' ORDER BY c.ordinal)
    FROM documents d JOIN chunks c ON c.doc_id = d.doc_id
    WHERE COALESCE(d.doc_state, 'active') = 'active'
    GROUP BY d.doc_id, d.file_path
    """
    with engine().begin() as conn:
        return [{"doc_id": r[0], "file_path": r[1], "text": r[2] or ""} for r in conn.execute(text(sql)).fetchall()]


def get_graph(force: bool = False) -> dict[str, dict[str, float]]:
    global _graph, _signature, _checked_at
    now = time.monotonic()
    if _graph is not None and not force and now - _checked_at < CHECK_INTERVAL_SECONDS:
        return _graph
    with _lock:
        signature = _db_signature()
        if _graph is None or force or signature != _signature:
            _graph = build_link_graph(_load_docs())
            _signature = signature
        _checked_at = time.monotonic()
        return _graph


def reset_cache() -> None:
    global _graph, _signature, _checked_at
    with _lock:
        _graph, _signature, _checked_at = None, None, 0.0


def _to_pgvector(vec) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in np.asarray(vec).tolist()) + "]"


def _best_chunks(doc_ids: list[str], query_emb, filters: dict | None):
    where = ["c.doc_id = ANY(:doc_ids)", "COALESCE(d.doc_state, 'active') = 'active'"]
    params: dict[str, Any] = {"doc_ids": doc_ids, "q": _to_pgvector(query_emb)}
    if filters and "source_type" in filters:
        where.append("d.source_type = ANY(:source_type)")
        params["source_type"] = filters["source_type"]
    if filters and "year_gte" in filters:
        where.append("d.year >= :year_gte")
        params["year_gte"] = int(filters["year_gte"])
    sql = f"""
    SELECT DISTINCT ON (c.doc_id)
           c.chunk_id, c.doc_id, c.ordinal, d.title, d.author, d.year, d.source_type,
           d.publisher, d.url, d.language, d.identifiers, c.content,
           1 - (e.embedding <=> CAST(:q AS vector)) AS score, c.section_path
    FROM embeddings e
    JOIN chunks c ON c.chunk_id = e.chunk_id
    JOIN documents d ON d.doc_id = c.doc_id
    WHERE {' AND '.join(where)}
    ORDER BY c.doc_id, (e.embedding <=> CAST(:q AS vector)) + 0, c.ordinal, c.chunk_id
    """
    with engine().begin() as conn:
        return conn.execute(text(sql), params).fetchall()


def linked_document_chunks(selected_doc_ids: list[str], query_emb, filters: dict | None = None) -> list:
    """Rows (same shape as vector_search) for the best chunk of documents linked
    from the first `graph_head` selected documents; at most `graph_add` rows."""
    if query_emb is None or not selected_doc_ids:
        return []
    if filters and "doc_id" in filters:
        return []  # the caller asked for specific documents; do not add others
    graph = get_graph()
    head = selected_doc_ids[: max(1, int(settings.graph_head))]
    present = set(selected_doc_ids)
    weight: dict[str, float] = {}
    for doc_id in head:
        neighbours = sorted(graph.get(doc_id, {}).items(), key=lambda x: (-x[1], x[0]))[: max(1, int(settings.graph_fan))]
        for nb, w in neighbours:
            if nb in present:
                continue
            weight[nb] = max(weight.get(nb, 0.0), min(1.0, float(w)))
    if not weight:
        return []
    rows = _best_chunks(sorted(weight.keys()), query_emb, filters)
    ranked = sorted(rows, key=lambda r: (-float(r[12]) * weight.get(r[1], 0.0), str(r[1])))
    return ranked[: max(0, int(settings.graph_add))]
