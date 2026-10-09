"""In-process BM25 over the indexed chunk text.

Why not Postgres full text: plainto_tsquery ANDs every word of the question, so
a natural-language question almost never matches a chunk, and ts_rank has no
inverse document frequency, so an OR query ranks by common words. Measured
2026-10-08 on the HAVEN docs (108 questions with gold documents): the AND
channel contributed nothing; BM25 fused with the vector ranking lifted
document-hit@5 from 40 % to 60 % before any other change.

The index is built from the database (active documents only) and rebuilt when
the chunk or document tables change. At tens of thousands of chunks that takes
a few seconds and a few tens of MB.
"""
from __future__ import annotations

import math
import re
import threading
import time
from collections import defaultdict
from typing import Any

from sqlalchemy import text

from app.rag.index.db import engine

_TOK_RE = re.compile(r"[A-Za-zÀ-ÿ0-9_]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Question words carry no retrieval signal; Norwegian and English.
STOPWORDS = frozenset("""a an the of to in on for and or is are be as at by it this that with from how what which why when
where do does can i you we my our your not no if then than into about should must will would there their
hva hvordan hvorfor hvilke hvilken hvilket når hvor er en et den det de som på i til av for og eller med
fra om kan skal må vil ikke jeg du vi man seg sin sitt sine har ha å at så bare også blir bli være var
""".split())


def tokenize(value: str) -> list[str]:
    """Lower-cased words, plus the parts of identifiers.

    `publisherAccess.issue` and `flow_element_skeleton` are also indexed as
    publisher/access/issue and flow/element/skeleton, so a question that spells
    an identifier in plain words still finds it.
    """
    raw = _TOK_RE.findall(value or "")
    tokens = [t.lower() for t in raw]
    for t in raw:
        parts = [p for p in _CAMEL_RE.sub("_", t).split("_") if p]
        if len(parts) > 1:
            tokens.extend(p.lower() for p in parts)
    return tokens


class BM25Index:
    def __init__(self, rows: list[dict[str, Any]], k1: float = 1.2, b: float = 0.75):
        self.rows = rows
        self.k1, self.b = k1, b
        self.n = len(rows)
        self.lengths: list[int] = []
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, row in enumerate(rows):
            tokens = tokenize(row["text"])
            self.lengths.append(len(tokens))
            tf: dict[str, int] = defaultdict(int)
            for t in tokens:
                tf[t] += 1
            for t, c in tf.items():
                self.postings[t].append((i, c))
        self.avg_len = (sum(self.lengths) / self.n) if self.n else 0.0

    def search(self, query: str, top_k: int, allowed=None) -> list[tuple[int, float]]:
        terms = [t for t in dict.fromkeys(tokenize(query)) if t not in STOPWORDS]
        scores: dict[int, float] = defaultdict(float)
        for t in terms:
            posting = self.postings.get(t)
            if not posting:
                continue
            idf = math.log(1 + (self.n - len(posting) + 0.5) / (len(posting) + 0.5))
            for i, c in posting:
                if allowed is not None and not allowed(self.rows[i]):
                    continue
                denom = c + self.k1 * (1 - self.b + self.b * self.lengths[i] / (self.avg_len or 1.0))
                scores[i] += idf * c * (self.k1 + 1) / denom
        ranked = sorted(scores.items(), key=lambda x: (-x[1], self.rows[x[0]]["doc_id"], self.rows[x[0]]["ordinal"],
                                                        self.rows[x[0]]["chunk_id"]))
        return ranked[:top_k]


_lock = threading.Lock()
_index: BM25Index | None = None
_signature: tuple | None = None
_checked_at = 0.0
CHECK_INTERVAL_SECONDS = 30.0


def _db_signature() -> tuple:
    sql = """
    SELECT (SELECT count(*) FROM chunks),
           (SELECT COALESCE(max(created_at)::text, '') FROM chunks),
           (SELECT count(*) FROM documents WHERE COALESCE(doc_state, 'active') = 'active'),
           (SELECT COALESCE(max(updated_at)::text, '') FROM documents)
    """
    with engine().begin() as conn:
        return tuple(conn.execute(text(sql)).fetchone())


def _load_rows() -> list[dict[str, Any]]:
    sql = """
    SELECT c.chunk_id, c.doc_id, c.ordinal, d.source_type, d.year, COALESCE(c.index_text, c.content)
    FROM chunks c JOIN documents d ON d.doc_id = c.doc_id
    WHERE COALESCE(d.doc_state, 'active') = 'active'
    ORDER BY c.doc_id, c.ordinal, c.chunk_id
    """
    with engine().begin() as conn:
        return [
            {"chunk_id": r[0], "doc_id": r[1], "ordinal": int(r[2] or 0), "source_type": r[3], "year": r[4], "text": r[5] or ""}
            for r in conn.execute(text(sql)).fetchall()
        ]


def get_index(force: bool = False) -> BM25Index:
    global _index, _signature, _checked_at
    now = time.monotonic()
    if _index is not None and not force and now - _checked_at < CHECK_INTERVAL_SECONDS:
        return _index
    with _lock:
        signature = _db_signature()
        if _index is None or force or signature != _signature:
            _index = BM25Index(_load_rows())
            _signature = signature
        _checked_at = time.monotonic()
        return _index


def reset_cache() -> None:
    global _index, _signature, _checked_at
    with _lock:
        _index, _signature, _checked_at = None, None, 0.0


def bm25_search(query: str, top_k: int = 50, filters: dict | None = None):
    """Same row shape as lexical_store.lexical_search (13 columns + section_path)."""
    filters = filters or {}
    source_types = set(filters["source_type"]) if "source_type" in filters else None
    doc_ids = set(filters["doc_id"]) if "doc_id" in filters else None
    year_gte = int(filters["year_gte"]) if "year_gte" in filters else None

    def allowed(row: dict[str, Any]) -> bool:
        if source_types is not None and row["source_type"] not in source_types:
            return False
        if doc_ids is not None and row["doc_id"] not in doc_ids:
            return False
        if year_gte is not None and (row["year"] is None or int(row["year"]) < year_gte):
            return False
        return True

    index = get_index()
    need_filter = source_types is not None or doc_ids is not None or year_gte is not None
    ranked = index.search(query, top_k, allowed if need_filter else None)
    if not ranked:
        return []
    score_by_id = {index.rows[i]["chunk_id"]: float(s) for i, s in ranked}
    sql = """
    SELECT c.chunk_id, c.doc_id, c.ordinal, d.title, d.author, d.year, d.source_type,
           d.publisher, d.url, d.language, d.identifiers, c.content, 0.0 AS score, c.section_path
    FROM chunks c JOIN documents d ON d.doc_id = c.doc_id
    WHERE c.chunk_id = ANY(:ids) AND COALESCE(d.doc_state, 'active') = 'active'
    """
    with engine().begin() as conn:
        rows = conn.execute(text(sql), {"ids": list(score_by_id.keys())}).fetchall()
    out = [tuple(r[:12]) + (score_by_id.get(r[0], 0.0), r[13]) for r in rows]
    out.sort(key=lambda r: (-r[12], str(r[1]), int(r[2] or 0), str(r[0])))
    return out
