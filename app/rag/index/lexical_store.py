from sqlalchemy import text
from app.rag.index.db import engine

def lexical_search(query: str, top_k: int = 50, filters: dict | None = None):
    filters = filters or {}
    where = ["c.content_tsv @@ plainto_tsquery('simple', :q)"]
    params = {"q": query, "top_k": top_k}

    if "year_gte" in filters:
        where.append("d.year >= :year_gte")
        params["year_gte"] = int(filters["year_gte"])
    if "source_type" in filters:
        where.append("d.source_type = ANY(:source_type)")
        params["source_type"] = filters["source_type"]

    where_sql = "WHERE " + " AND ".join(where)

    sql = f'''
    SELECT c.chunk_id, c.doc_id, c.ordinal, d.title, d.author, d.year, d.source_type,
           d.publisher, d.url, d.language, d.identifiers,
           c.content,
           ts_rank_cd(c.content_tsv, plainto_tsquery('simple', :q)) AS score
    FROM chunks c
    JOIN documents d ON d.doc_id = c.doc_id
    {where_sql}
    ORDER BY score DESC, c.doc_id, c.ordinal, c.chunk_id
    LIMIT :top_k
    '''
    with engine().begin() as conn:
        return conn.execute(text(sql), params).fetchall()
