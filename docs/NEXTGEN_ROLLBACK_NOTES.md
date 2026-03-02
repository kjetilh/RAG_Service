# Next-gen RAG Rollback Notes

Denne filen beskriver rollback per leveranse-commit (PR1..PR6).

## PR1: doc_state + versioning migration

Commit: `PR1: add doc_state versioning migration and runner`

Endringer:
- ny migrasjon `app/rag/index/migrations/0001_doc_state_versioning.sql`
- ny runner `scripts/apply_migrations.py`
- schema utvidet med doc lifecycle-kolonner

Rollback:
1. Sett tjenesten tilbake til commit før PR1.
2. La kolonnene stå i databasen (ikke-destruktiv rollback anbefales).
3. Hvis hard rollback av schema kreves, ta full DB-backup før `ALTER TABLE ... DROP COLUMN`.

## PR2: strict rag_cases YAML loader

Commit: `PR2: add strict rag_cases YAML loader`

Endringer:
- `app/rag/cases/loader.py`
- `config/rag_cases.yml`

Rollback:
1. Sett `NEXT_GEN_RAG_ENABLED=false`.
2. Fjern bruk av `RAG_CASES_PATH` og deaktiver nye case-spesifikke flyter.
3. Reverter commit hvis kodefjerning er ønsket.

## PR3: deterministic planner + stable trace

Commit: `PR3: add deterministic planner and stable retrieval trace`

Endringer:
- planner bak feature flag
- deterministisk retrieval/sortering

Rollback:
1. Sett `NEXT_GEN_RAG_ENABLED=false`.
2. API fortsetter med legacy router-flyt.
3. Reverter commit for full tilbakeføring av plannerkode.

## PR4: tombstone sync + anti-thrash batching

Commit: `PR4: add tombstone sync with anti-thrash batching`

Endringer:
- tombstone state transitions i `sync_folder.py`
- anti-thrash grace + batching

Rollback:
1. Sett `SYNC_TOMBSTONE_ENABLED=false`.
2. (Valgfritt) behold tombstoned rows; ingen hard delete nødvendig.
3. Reverter commit for å gå tilbake til tidligere hard-delete sync.

## PR5: evaluation gate runner

Commit: `PR5: add evaluation gate runner from rag case thresholds`

Endringer:
- `app/rag/eval/gate.py`
- pipeline-integrasjon med optional enforcement

Rollback:
1. Sett `NEXT_GEN_RAG_ENABLED=false` eller bruk `enforce: false` i alle cases.
2. Reverter commit for å fjerne gate-evaluering helt.

## PR6: /v1/query + backward-compatible shim

Commit: `PR6: add /v1/query endpoint with backward-compatible chat shim`

Endringer:
- nytt endpoint `POST /v1/query`
- `/v1/chat` fungerer fortsatt via shim

Rollback:
1. Klienter kan fortsette å bruke `/v1/chat` uten endring.
2. Reverter commit for å fjerne `/v1/query` helt.

## Operasjonell rollback-strategi

1. Reverter én commit av gangen (PR6 -> PR1) for minst mulig risiko.
2. Kjør `python -m scripts.rebuild_index` etter rollback av schema-relatert kode.
3. Verifiser:
   - `GET /health`
   - `POST /v1/chat`
   - admin sync-endepunkt med `dry_run=true`.
