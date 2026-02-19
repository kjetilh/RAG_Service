CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
  doc_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT,
  year INT,
  source_type TEXT,
  content_hash TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  section_path TEXT,
  ordinal INT NOT NULL,
  content TEXT NOT NULL,
  content_tsv tsvector,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS embeddings (
  chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
  embedding vector(384) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING GIN (content_tsv);
CREATE INDEX IF NOT EXISTS idx_embeddings_vec ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Optional metadata enrichment (migration-safe)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS publisher TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS url TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS language TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS identifiers JSONB;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS meta_sources JSONB;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_path TEXT;
