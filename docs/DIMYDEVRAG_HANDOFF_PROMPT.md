# Handoff Prompt: Bootstrap DiMyDevRAG

Copy this prompt into a fresh Codex/agent thread opened with cwd:

`/Users/kjetil/Build/Digipomps/HAVEN/DiMyDevRAG`

---

You are working in `/Users/kjetil/Build/Digipomps/HAVEN/DiMyDevRAG`.

This folder is expected to be empty or nearly empty. Your job is to bootstrap it into a practical, private DiMy developer-documentation RAG project. Do not assume the shape of the project before inspecting the local repos. Start with repo inspection, then create the smallest useful project structure, docs, manifests, and scripts/configs needed for another agent or developer to keep a private DiMy/HAVEN developer corpus synced into `rag_service`.

## Goal

Create the first useful version of `DiMyDevRAG`: a repo or project folder that owns the corpus policy, source classification, sync manifests, runbooks, and verification workflow for a private DiMy developer RAG.

This project should not reimplement the RAG engine. The RAG engine already lives in:

`/Users/kjetil/Documents/Bokprosjekt_Innovasjonsledelse/rag_service`

Instead, DiMyDevRAG should make it easy to build and maintain a curated private developer corpus from HAVEN/DiMy sources such as CellScaffold documentation, CellProtocol docs, and relevant operational/developer notes.

## Important Current Context

- `rag_service` already defines `dimy_docs` and `dimy_prompts` in `config/rag_cases.yml`.
- `rag_service` already has multi-RAG deployment docs and a `rag_dimy_api` / `rag_dimy_db` shape.
- The current safe recommendation is: use a separate private DiMy docs instance or locked-down internal service first, not a public case containing private docs.
- Public `rag_service` chat/query/case routes are case-filtered, but not user-authorized.
- Public document download is especially sensitive: `/v1/documents/{doc_id}/download` must not expose private source files.
- Research routes have token/case-scope support. Cell routes can enforce case roles when `CELL_ACCESS_CONTROL_ENABLED=true`.
- Prior runtime checks found old/tombstoned/stale local RAG runtime state at times, so always verify the live service before claiming corpus freshness.

## Read First

Inspect the empty folder:

```bash
pwd
find . -maxdepth 3 -print
git status --short
```

Then inspect these upstream references:

```bash
cd /Users/kjetil/Documents/Bokprosjekt_Innovasjonsledelse/rag_service
sed -n '1,220p' config/rag_cases.yml
sed -n '1,260p' docs/DEPLOY_VPS_MULTI_RAG.md
sed -n '1,220p' docs/SYNC_ORCHESTRATOR.md
sed -n '1,220p' docs/RAG_CASES_SCHEMA.md
sed -n '1,220p' docs/RAG_CELLPROTOCOL_ACCESSIBILITY_REPORT.md
sed -n '1,220p' app/rag/cases/visibility.py
sed -n '1,260p' app/api/routes_research.py
sed -n '1,280p' app/api/routes_cell.py
sed -n '1,330p' app/api/routes_chat.py
```

Inspect candidate source folders before designing the corpus:

```bash
find /Users/kjetil/Build/Digipomps/HAVEN/CellScaffold/Documentation -maxdepth 2 -type f | head -80
find /Users/kjetil/Build/Digipomps/HAVEN/CellScaffold/Documentation -maxdepth 2 -type d | sort
find /Users/kjetil/Build/Digipomps/HAVEN/CellProtocolDocuments -maxdepth 3 -type f | head -80
find /Users/kjetil/Build/Digipomps/HAVEN/CellProtocol -maxdepth 3 -type f \( -name '*.md' -o -name '*.markdown' -o -name '*.txt' \) | head -80
```

If any expected source path is missing, say so explicitly and continue with the paths that exist.

## Build This Project

Create a small, durable structure in `DiMyDevRAG`. Suggested first version:

```text
README.md
AGENTS.md
config/
  dimy_dev_sources.yml
  sync_orchestrator.dimydevrag.example.toml
docs/
  ACCESS_MODEL.md
  CORPUS_POLICY.md
  INGEST_RUNBOOK.md
  SOURCE_CLASSIFICATION.md
  VERIFICATION.md
scripts/
  build_source_manifest.py
  verify_source_manifest.py
```

Keep it practical. If a script would be speculative, write the policy/runbook first and leave script stubs with explicit TODOs only where needed.

## Corpus Policy To Encode

Classify source material before ingest:

- `public_reference`: docs that are safe to include in open or broadly shared developer RAG.
- `internal_dev`: useful developer/ops/design docs that should be private to HAVEN/DiMy developers.
- `sensitive_or_review`: AIModelRuns, research data, test fixtures, logs, private operations notes, generated outputs, zip archives, or anything with personal data, credentials, private URLs, or ambiguous provenance.
- `exclude`: `.DS_Store`, archives by default, binaries/images unless explicitly needed, generated bundles, and anything not useful for text retrieval.

Do not ingest all of `CellScaffold/Documentation` blindly. Start with an allowlist, then document each exclusion category and why.

Recommended initial source types:

- `cellprotocol_docs`
- `haven_docs`
- `cellscaffold_internal_docs`
- `dimy_private_dev_docs`
- optionally `dimy_prompt_docs` if prompt/workspace composition docs are separated

Avoid reusing a single broad `haven_docs` source type for private and public material unless the service instance is fully private.

## Access/Security Requirements

Assume this corpus may contain non-public project documentation.

Minimum safe v0:

- private or internal-only RAG instance
- explicit `INSTANCE_CASE_IDS_JSON`
- unique admin key and DB credentials
- no public source downloads for private docs
- prefer `/v1/research/*` with scoped tokens or `/v1/cell/*` with `CELL_ACCESS_CONTROL_ENABLED=true`
- document how `RAG_DIMY_CELL_ACCESS_CONTROL_ENABLED`, `RAG_DIMY_CELL_GATEWAY_SHARED_SECRET`, `RAG_DIMY_CELL_OWNER_USER_IDS_JSON`, and `RAG_DIMY_RESEARCH_API_TOKENS_JSON` should be set
- do not claim document-level ACL exists unless you implement and test it

If you find that the current `rag_service` public endpoints would expose private files, call that out as a blocker for public deployment.

## Sync/Runtime Requirements

The project should be able to explain how to:

1. Build a source manifest from allowed local files.
2. Mirror allowed files into the DiMy RAG upload/live folder.
3. Run `scripts.sync_orchestrator` or equivalent against `rag_dimy_api`.
4. Run a dry-run before destructive sync.
5. Verify the live API routes with `scripts/rag_runtime_check.py`.
6. Verify corpus status using `/v1/cases/{case_id}/status`, `/v1/research/cases/{case_id}/status`, or the CLI if available.
7. Report corpus freshness from live DB/API state, not from file timestamps alone.

## Engineering Constraints

- Do not rewrite or move files in upstream repos.
- Do not copy large private corpora into DiMyDevRAG unless explicitly needed; prefer manifests and sync config.
- Do not put secrets in files. Use `.env.example` placeholders only.
- Keep generated docs clear about what is implemented now vs. what is planned.
- If you need to change `rag_service`, stop and propose the patch separately unless the user explicitly asks you to edit it.
- The workspace may be dirty. Do not revert unrelated changes.

## Verification

At minimum:

```bash
find . -maxdepth 3 -type f | sort
python3 -m py_compile scripts/*.py
```

If Python dependencies or runtime services are unavailable, say exactly what could not be verified.

If you create YAML/TOML, run a syntax parse with available standard or project tools. If no parser is available without installing dependencies, say so and keep the files simple.

## Deliverables

End with:

- files created
- source paths inspected
- recommended initial include/exclude policy
- exact commands for the next operator to run
- what was verified
- what remains blocked or intentionally not done

Do not answer with only a plan. Bootstrap the folder into a usable first version.
