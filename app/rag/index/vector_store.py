import numpy as np
from sqlalchemy import text
from app.rag.index.db import engine
from app.settings import settings

def _to_pgvector(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in vec.tolist()) + "]"

def upsert_embedding(chunk_id: str, embedding: np.ndarray) -> None:
    sql = '''
    INSERT INTO embeddings(chunk_id, embedding)
    VALUES (:chunk_id, CAST(:embedding AS vector))
    ON CONFLICT (chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding
    '''
    with engine().begin() as conn:
        conn.execute(text(sql), {"chunk_id": chunk_id, "embedding": _to_pgvector(embedding)})

def vector_search(query_embedding: np.ndarray, top_k: int = 50, filters: dict | None = None):
    filters = filters or {}
    where = ["COALESCE(d.doc_state, 'active') = 'active'"]
    params = {"q": _to_pgvector(query_embedding), "top_k": top_k}
    if "year_gte" in filters:
        where.append("d.year >= :year_gte")
        params["year_gte"] = int(filters["year_gte"])
    if "source_type" in filters:
        where.append("d.source_type = ANY(:source_type)")
        params["source_type"] = filters["source_type"]
    if "doc_id" in filters:
        where.append("d.doc_id = ANY(:doc_id)")
        params["doc_id"] = filters["doc_id"]
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    # ivfflat with probes=1 looks at roughly one list in a hundred, and the
    # source_type/doc_state filter is applied after that, so the "top 50" can be
    # both incomplete and wrong. "+ 0" keeps the planner from using the
    # approximate index: one statement, exact order, a few ms at this size.
    order_expr = "(e.embedding <=> CAST(:q AS vector)) + 0" if bool(getattr(settings, "vector_exact_search", True)) \
        else "e.embedding <=> CAST(:q AS vector)"

    sql = f'''
    SELECT c.chunk_id, c.doc_id, c.ordinal, d.title, d.author, d.year, d.source_type,
           d.publisher, d.url, d.language, d.identifiers,
           c.content,
           1 - (e.embedding <=> CAST(:q AS vector)) AS score,
           c.section_path
    FROM embeddings e
    JOIN chunks c ON c.chunk_id = e.chunk_id
    JOIN documents d ON d.doc_id = c.doc_id
    {where_sql}
    ORDER BY {order_expr}, c.doc_id, c.ordinal, c.chunk_id
    LIMIT :top_k
    '''
    with engine().begin() as conn:
        return conn.execute(text(sql), params).fetchall()
