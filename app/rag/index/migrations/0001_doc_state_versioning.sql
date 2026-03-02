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

UPDATE documents
SET updated_at = COALESCE(updated_at, created_at, now())
WHERE updated_at IS NULL;
