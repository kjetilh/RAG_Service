# RAG Service API Endepunkter

Dette dokumentet er en eksplisitt oversikt over HTTP-endepunktene som er registrert i FastAPI-appen per `app/main.py`.

Kilde for routing:

- `app/main.py`
- `app/api/routes_ui.py`
- `app/api/routes_chat.py`
- `app/api/routes_admin.py`
- `app/api/routes_cell.py`
- `app/api/routes_interviews.py`
- `app/api/routes_research.py`

## Kategorier

Tjenesten har disse route-gruppene:

- UI og health
- chat og query
- admin
- cell gateway
- interviews
- research

## UI og health

### `GET /`

- Leverer `app/static/chat.html`
- Definert i `app/api/routes_ui.py`
- `include_in_schema=False`

### `GET /health`

- Returnerer `{"ok": true}`
- Definert direkte i `app/main.py`

## Chat og query

Disse endepunktene er vanlige query/chat-endepunkter.

### `POST /v1/query`

- Request: `QueryRequest`
- Respons: `QueryResponse`
- Returnerer `answer`, `citations`, `retrieval_debug` og `trace`
- Definert i `app/api/routes_chat.py`

### `POST /v1/chat`

- Request: `ChatRequest`
- Respons: `ChatResponse`
- Definert i `app/api/routes_chat.py`

### `POST /v1/chat/stream`

- SSE-endepunkt for streaming
- Sender eventene `citations`, `delta` og `done`
- Definert i `app/api/routes_chat.py`

### `GET /v1/documents/{doc_id}/download`

- Laster ned filen som er registrert for et dokument
- Brukes av eksisterende klienter
- Definert i `app/api/routes_chat.py`

## Admin

Disse endepunktene krever `X-API-Key`.

### `POST /v1/admin/rebuild`

- Rebuilder index-tabeller
- Krever `confirm=true`
- Definert i `app/api/routes_admin.py`

### `POST /v1/admin/ingest`

- Ingest av filer fra mappe
- Definert i `app/api/routes_admin.py`

### `POST /v1/admin/sync`

- Synkroniserer live-mapper mot dokumenttabellen
- Stotter `delete_missing`, `dry_run`, `tombstone_mode`, `tombstone_grace_seconds` og `anti_thrash_batch_size`
- Definert i `app/api/routes_admin.py`

### `GET /v1/admin/coverage-report`

- Returnerer coverage-rapport
- Definert i `app/api/routes_admin.py`

### `GET /v1/admin/coverage-actions`

- Returnerer prioriterte coverage-tiltak
- Definert i `app/api/routes_admin.py`

### `GET /v1/admin/prompt-config`

- Leser aktiv prompt-konfigurasjon
- Definert i `app/api/routes_admin.py`

### `PUT /v1/admin/prompt-config`

- Oppdaterer runtime prompt-konfigurasjon
- Definert i `app/api/routes_admin.py`

## Cell gateway

Disse endepunktene er laget for CellScaffold og annen celleintegrasjon.

Autentisering:

- `X-Cell-Gateway-Secret` + `X-Cell-User-Id`
- eller `X-API-Key` for admin-overstyring

### `GET /v1/cell/cases`

- Lister tilgjengelige RAG-cases for brukeren
- Definert i `app/api/routes_cell.py`

### `POST /v1/cell/cases/{case_id}/query`

- Kjører query innenfor ett case
- Definert i `app/api/routes_cell.py`

### `POST /v1/cell/cases/{case_id}/interviews/collective-summary`

- Kjører kollektiv intervjuanalyse innenfor ett case
- Definert i `app/api/routes_cell.py`

### `GET /v1/cell/cases/{case_id}/corpus`

- Lister corpus for ett case
- Definert i `app/api/routes_cell.py`

### `GET /v1/cell/cases/{case_id}/links`

- Returnerer linkgraph for et case
- Definert i `app/api/routes_cell.py`

### `GET /v1/cell/cases/{case_id}/documents/{doc_id}/links`

- Returnerer linkgraph for ett dokument
- Definert i `app/api/routes_cell.py`

### `GET /v1/cell/cases/{case_id}/members`

- Lister medlemmer og roller for et case
- Definert i `app/api/routes_cell.py`

### `PUT /v1/cell/cases/{case_id}/members/{target_user_id}`

- Setter rolle for en bruker i et case
- Definert i `app/api/routes_cell.py`

### `DELETE /v1/cell/cases/{case_id}/members/{target_user_id}`

- Fjerner en bruker fra et case
- Definert i `app/api/routes_cell.py`

## Interviews

Dette er et direkte API for kollektiv intervjuanalyse uten cellegateway.

### `POST /v1/interviews/collective-summary`

- Request: `CollectiveSummaryRequest`
- Respons: `CollectiveSummaryResponse`
- Definert i `app/api/routes_interviews.py`

## Research

Disse endepunktene er read-only og laget for Deep Research, dokumentoppslag og promptoppslag.

Autentisering:

- `Authorization: Bearer <token>`
- nedlasting kan bruke signert URL fra `download_url`

### `GET /v1/research/cases`

- Lister enabled cases tokenet har tilgang til
- Definert i `app/api/routes_research.py`

### `POST /v1/research/query`

- Kjører read-only query mot et valgt case
- Definert i `app/api/routes_research.py`

### `GET /v1/research/cases/{case_id}/corpus`

- Lister dokumenter i corpus for et case
- Definert i `app/api/routes_research.py`

### `GET /v1/research/cases/{case_id}/links`

- Returnerer linkgraph for et helt case
- Definert i `app/api/routes_research.py`

### `GET /v1/research/cases/{case_id}/documents/{doc_id}/links`

- Returnerer linkgraph for ett dokument i et case
- Definert i `app/api/routes_research.py`

### `GET /v1/research/documents/{doc_id}/download`

- Laster ned kildedokument via bearer-token eller signert URL
- Definert i `app/api/routes_research.py`

## Kort auth-matrise

- `GET /`, `GET /health`: ingen egen API-auth i appen
- chat/query: ingen egen API-auth i appen
- admin: `X-API-Key`
- cell: `X-Cell-Gateway-Secret` + `X-Cell-User-Id`, eller admin key
- research: `Authorization: Bearer <token>`

## Viktig avgrensing

- `chat` og `query` er ikke det samme som `research`
- `research` er read-only og skal ikke brukes for ingest, sync eller admin-operasjoner
- `cell` er ikke det samme som `research`; cell-endepunktene har egen gateway-auth og medlemskapsmodell
- eldre filnedlasting finnes fortsatt som `GET /v1/documents/{doc_id}/download`, mens ny research-bruk bor bruke `GET /v1/research/documents/{doc_id}/download`
