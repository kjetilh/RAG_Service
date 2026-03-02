CREATE TABLE IF NOT EXISTS rag_case_access (
  case_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  assigned_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (case_id, user_id)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_rag_case_access_role'
  ) THEN
    ALTER TABLE rag_case_access
      ADD CONSTRAINT chk_rag_case_access_role
      CHECK (role IN ('owner', 'admin', 'viewer'));
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_rag_case_access_user ON rag_case_access(user_id);
CREATE INDEX IF NOT EXISTS idx_rag_case_access_case_role ON rag_case_access(case_id, role);
