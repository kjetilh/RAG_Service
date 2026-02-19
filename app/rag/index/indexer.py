from __future__ import annotations
from pathlib import Path
from sqlalchemy import text
from app.rag.index.db import engine
from app.rag.ingest.loaders import load_any
from app.rag.ingest.cleaner import clean_text
from app.rag.ingest.chunker import chunk_text
from app.rag.ingest.metadata import compute_hash, make_doc_id
from app.rag.ingest.metadata_extractor import extract_metadata
from app.rag.index.embedder import default_embedder
from app.rag.index.vector_store import upsert_embedding

def upsert_document(doc_id: str, title: str, author: str | None, year: int | None, source_type: str | None, content_hash: str,
                   publisher: str | None = None, url: str | None = None, language: str | None = None,
                   identifiers_json: str | None = None, meta_sources_json: str | None = None, file_path: str | None = None):
    sql = '''
    INSERT INTO documents(doc_id, title, author, year, source_type, content_hash, publisher, url, language, identifiers, meta_sources, file_path)
    VALUES (:doc_id, :title, :author, :year, :source_type, :content_hash, :publisher, :url, :language,
            CAST(:identifiers_json AS jsonb), CAST(:meta_sources_json AS jsonb), :file_path)
    ON CONFLICT (doc_id) DO UPDATE SET
      title=EXCLUDED.title, author=EXCLUDED.author, year=EXCLUDED.year,
      source_type=EXCLUDED.source_type, content_hash=EXCLUDED.content_hash,
      publisher=EXCLUDED.publisher, url=EXCLUDED.url, language=EXCLUDED.language,
      identifiers=EXCLUDED.identifiers, meta_sources=EXCLUDED.meta_sources, file_path=EXCLUDED.file_path
    '''
    with engine().begin() as conn:
        conn.execute(text(sql), {
            "doc_id": doc_id,
            "title": title,
            "author": author,
            "year": year,
            "source_type": source_type,
            "content_hash": content_hash,
            "publisher": publisher,
            "url": url,
            "language": language,
            "identifiers_json": identifiers_json,
            "meta_sources_json": meta_sources_json,
            "file_path": file_path,
        })

def upsert_chunk(chunk_id: str, doc_id: str, section_path: str | None, ordinal: int, content: str):
    # Postgres TEXT cannot contain NUL bytes (0x00)
    content = content.replace("\x00", "")
    sql = '''
    INSERT INTO chunks(chunk_id, doc_id, section_path, ordinal, content, content_tsv)
    VALUES (:chunk_id, :doc_id, :section_path, :ordinal, :content, to_tsvector('simple', :content))
    ON CONFLICT (chunk_id) DO UPDATE SET
      content=EXCLUDED.content, content_tsv=EXCLUDED.content_tsv,
      section_path=EXCLUDED.section_path, ordinal=EXCLUDED.ordinal
    '''
    with engine().begin() as conn:
        conn.execute(text(sql), {"chunk_id": chunk_id, "doc_id": doc_id, "section_path": section_path,
                                 "ordinal": ordinal, "content": content})

def ingest_file(path: Path, source_type: str | None = None, author: str | None = None, year: int | None = None) -> str:
    raw = load_any(path)
    txt = clean_text(raw)
    h = compute_hash(txt)
    doc_id = make_doc_id(path, h)
    title = path.stem

    preview = txt[:12000] if txt else ""
    meta = extract_metadata(path=path, preview_text=preview, source_type=source_type, cli_author=author, cli_year=year, cli_title=title)
    upsert_document(doc_id, meta.title, meta.author, meta.year, meta.source_type, h,
                  publisher=meta.publisher, url=meta.url, language=meta.language,
                  identifiers_json=meta.identifiers_json, meta_sources_json=meta.meta_sources_json,
                  file_path=meta.file_path)

    chunks = chunk_text(doc_id, txt)
    for ch in chunks:
        upsert_chunk(ch.chunk_id, ch.doc_id, ch.section_path, ch.ordinal, ch.content)

    embedder = default_embedder()
    vecs = embedder.embed([c.content for c in chunks])
    for ch, v in zip(chunks, vecs):
        upsert_embedding(ch.chunk_id, v)
    return doc_id
