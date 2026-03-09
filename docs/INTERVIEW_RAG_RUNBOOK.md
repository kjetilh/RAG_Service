# Runbook: Intervju-RAG for bokprosjektet

## 1) Formater transkripsjoner

Bruk fast mal per intervju (Markdown anbefales):

```md
# Interview: <interview_id>
Dato: YYYY-MM-DD
Rolle: <lederrolle>
Virksomhetstype: <sektor/bedrift>

## Q1: <spørsmål 1>
<transkribert svar>

## Q2: <spørsmål 2>
<transkribert svar>
```

Poenget er at hver `Q*` blir eget heading-segment i chunking.

## 2) Ingest

Legg filer under ingest-root og sync med source type:

```bash
curl -s -X POST http://127.0.0.1:8102/v1/admin/sync \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $RAG_DIMY_ADMIN_API_KEY" \
  -d '{
    "path": "intervjuer/live",
    "source_type": "innovasjon_intervju_transcript",
    "delete_missing": true
  }'
```

## 3) Kjør query mot intervju-case

```bash
curl -s -X POST http://127.0.0.1:8102/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Hva er samlet syn på de viktigste innovasjonsbarrierene?",
    "case_id": "innovasjon_intervjuer",
    "model_profile": "gpt-4o-mini"
  }'
```

## 4) Sett intervju-promptprofil (valgfritt)

Bruk admin-endepunkt for å bytte persona/template i intervju-instansen:

```bash
curl -s -X PUT http://127.0.0.1:8102/v1/admin/prompt-config \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $RAG_DIMY_ADMIN_API_KEY" \
  -d '{
    "system_persona_path": "prompts/system_persona_interview.md",
    "answer_template_path": "prompts/answer_template_interview.md",
    "updated_by": "ops",
    "change_note": "intervjuanalyse v1"
  }'
```

## 5) Kollektiv mening per fast spørsmål

API (ny):

- `POST /v1/interviews/collective-summary`
  - bruker `case_id` + spørsmål fra fil eller inline.
- `POST /v1/cell/cases/{case_id}/interviews/collective-summary`
  - samme logikk, men med case tvunget av URL + RBAC for scaffold-kall.

Eksempel (direkte API):

```bash
curl -s -X POST http://127.0.0.1:8102/v1/interviews/collective-summary \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "innovasjon_intervjuer",
    "question_set_path": "config/interview_questions.example.yml",
    "model_profile": "gpt-4o-mini"
  }'
```

V2 (anbefalt neste implementasjon):

- Utvid med eksplisitt enighet/uenighet-score og dekningsscore per spørsmål i samme response.

## 6) CellScaffold-kobling

Bruk eksisterende `/rag-mvp/api/*` i scaffold:

- `cases` for casevalg.
- `query` for per-spørsmål analyse.
- `corpus` for å sjekke dekning.
- `links` for navigering mellom dokumenter.

## 7) Research-prompt

Hvis du vil validere designet mot ekstern metodekunnskap:

- `docs/DEEP_RESEARCH_INTERVIEW_RAG_PROMPT.md`
