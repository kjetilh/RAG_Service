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

-- Document lifecycle/state (next-gen RAG, migration-safe)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_version INT NOT NULL DEFAULT 1;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS replaced_by_doc_id TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS state_reason TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS tombstoned_at TIMESTAMPTZ;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_documents_doc_state'
  ) THEN
    ALTER TABLE documents
      ADD CONSTRAINT chk_documents_doc_state
      CHECK (doc_state IN ('active', 'tombstone_pending', 'tombstone'));
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_documents_state ON documents(doc_state);
CREATE INDEX IF NOT EXISTS idx_documents_source_state ON documents(source_type, doc_state);
CREATE INDEX IF NOT EXISTS idx_documents_file_state ON documents(file_path, source_type, doc_state);

-- Runtime prompt config (singleton, migration-safe)
CREATE TABLE IF NOT EXISTS prompt_runtime_config (
  id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  system_persona_path TEXT,
  answer_template_path TEXT,
  version INT NOT NULL DEFAULT 0,
  updated_by TEXT,
  change_note TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO prompt_runtime_config (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;
