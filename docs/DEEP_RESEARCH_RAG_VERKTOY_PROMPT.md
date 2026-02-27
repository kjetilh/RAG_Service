# Deep Research Brief - neste generasjon dokumentasjons-RAG

Dette dokumentet er laget for a kopieres inn i ChatGPT Deep Research.

## 1) Kontekstpakke (dagens system)

- Stack: FastAPI + PostgreSQL/pgvector + hybrid retrieval (lexical + vector).
- Tjenester i drift:
  - `rag_innovasjon_api` (domene: innovasjon)
  - `rag_dimy_api` (domene: dokumentasjon/prompt)
- Model routing per request: `model_profile`.
- Promptstyring:
  - per service via env (`SYSTEM_PERSONA_PATH`, `ANSWER_TEMPLATE_PATH`)
  - runtime override via DB-tabell `prompt_runtime_config` og admin-endepunkt.
- Nye admin-endepunkter:
  - `POST /v1/admin/ingest` (batch, flytter filer til `done/failed`)
  - `POST /v1/admin/sync` (kontinuerlig synk, flytter ikke filer)
  - `GET/PUT /v1/admin/prompt-config`
- Dokumentmetadata lagres bl.a. med `source_type`, `file_path`, `content_hash`.

## 2) Problem som skal loses

Vi vil bygge et bedre verktøy for:

1. kontinuerlig synk av dokumentasjon og prompts (opprett, endre, slett)
2. bedre navigering i dokumentasjon (hva finnes, hvor henger ting sammen, hvor er hull)
3. mer presise svar uten hallusinasjon
4. enkel oppsett av nye RAG-caser (konfig-drevet, ikke hardkodet)

Vi vurderer to strategier:

- A) Egen RAG for prompts + egen RAG for dokumentasjon + overliggende router/orkestrator
- B) En felles RAG med tydelig metadatafiltrering og query-planlegging

## 3) Krav og rammer

- Svar skal være kildeforankret og saklige.
- Hvis dokumentasjon er mangelfull/inkonsistent skal systemet si fra.
- Løsningen må støtte flere domener og flere modellprofiler.
- Drift skal være enkel pa VPS med Docker Compose.
- Systemet må kunne brukes av teknisk kyndige utviklere (Vegar, Kjetil, andre utviklere).

## 4) Oppdrag til Deep Research

Gi en forskningsbasert anbefaling for arkitektur og drift av neste versjon.
Bruk primærkilder (papers, offisiell dokumentasjon, relevante standarder).

Besvar:

1. Bør vi splitte prompts og dokumentasjon i hver sin RAG, eller ha en felles index med metadata-router?
2. Hvordan bor en overliggende "query planner/router" bygges for a velge:
   - indeks/rag-case
   - promptprofil
   - retrieval-strategi (f.eks. top-k, rerank, query rewrite)
3. Hvilket design gir best balanse mellom presisjon, transparens og driftskostnad?
4. Hvordan detektere og rapportere dokumentasjonshull automatisk?
5. Hvilken konfigmodell bor brukes for enkel onboarding av nye RAG-cases?
   - eksempel: `rag_cases/<case>.yaml` med ingest-kilder, metadataregler, router-regler, promptprofiler
6. Hvordan implementere robust synk for filer (nye/endrede/slettede) uten indekstrash?
7. Hvordan evaluere kvalitet kontinuerlig (metrics, testsett, regresjonsgates)?

## 5) Forventet leveranseformat

Lever svaret i disse seksjonene:

1. **Executive summary (maks 12 punkter)**
2. **Alternativer og beslutningsmatrise**:
   - A: separerte RAG-er + router
   - B: felles RAG + metadata/router
   - C: hybrid variant
   - vurdering pa: presisjon, kompleksitet, kostnad, drift, skalerbarhet
3. **Anbefalt target-arkitektur**:
   - komponentdiagram (tekstlig)
   - dataflyt for ingest/sync/query
4. **Konfig-drevet modell for nye RAG-cases**:
   - konkret forslag til config-schema
   - eksempelkonfig for `dimy_docs`, `dimy_prompts`, `innovasjon`
5. **Implementasjonsplan i faser (0-90 dager)**:
   - fase 1: lav risiko
   - fase 2: router og kvalitetsmåling
   - fase 3: avansert forbedring
6. **Risikoer, feilmåter og mottiltak**:
   - hallucinasjon
   - stale index
   - routing-feil
   - driftssikkerhet

## 6) Prompt (kopier alt under)

```text
You are a senior RAG architect and applied research analyst.
I need a research-backed recommendation for the next version of our domain-specific RAG platform.

Context:
- We run FastAPI + PostgreSQL/pgvector with hybrid retrieval (lexical + vector).
- We currently have two services:
  - rag_innovasjon_api (innovation domain)
  - rag_dimy_api (documentation/prompt domain)
- We support model_profile routing per request.
- Prompt config is both env-driven and DB-overridable (prompt_runtime_config with GET/PUT admin endpoint).
- We now have two ingestion styles:
  - batch ingest (moves files to done/failed)
  - sync ingest (keeps files in place and syncs create/update/delete)
- We need a better documentation exploration tool and stronger signal on documentation gaps.

Primary questions:
1) Should we split prompts and documentation into separate RAG indexes/services, or keep one shared index with metadata-based routing?
2) How should a top-layer query planner/router decide index, prompt profile, and retrieval strategy dynamically?
3) What architecture best balances precision, traceability, operations simplicity, and cost?
4) How do we systematically detect missing/inconsistent documentation and surface improvement opportunities?
5) How should we design a configuration-driven “RAG case” model so new domains are easy to add?

Constraints:
- Answers must be grounded and non-hallucinated.
- Must support multiple domains and model profiles.
- Must run simply in Docker on a VPS.
- Audience is technically strong developers who need practical implementation guidance.

Please deliver:
1) Executive summary (max 12 bullets)
2) Decision matrix comparing:
   A) separate doc/prompt RAG + router
   B) shared index + metadata router
   C) hybrid approach
   with scoring across precision, complexity, cost, operability, scalability
3) Recommended target architecture with text diagram and data flows
4) Config-driven case model proposal (schema + examples for dimy_docs, dimy_prompts, innovasjon)
5) 0-90 day phased implementation plan
6) Risks/failure modes and mitigations
7) Metrics and evaluation strategy (retrieval quality, grounding quality, usefulness, freshness)

Use primary sources where possible (papers, official docs) and cite them.
Clearly separate “evidence-backed” claims from your own inference.
```
