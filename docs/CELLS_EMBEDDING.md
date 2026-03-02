# CellScaffold embedding av RAG

Dette dokumentet beskriver hvordan RAG-tjenesten kobles inn i CellScaffold med tilgangskontroll, corpus-utforskning og lenkenavigering.

## Mål

- Eier skal ha full admin-kontroll.
- Eier skal kunne gi andre `admin`/`viewer` per RAG-case.
- Celler skal kunne:
  - spørre RAG (`query`)
  - vise hele corpus (`corpus`)
  - følge dokumentlenker (`links`)
- Løsningen skal støtte flere case-konfigurasjoner via `config/rag_cases.yml`.

## Sikkerhetsmodell (RBAC)

- Feature flag: `CELL_ACCESS_CONTROL_ENABLED=true`
- Gateway-hemmelighet: `CELL_GATEWAY_SHARED_SECRET`
- Bootstrap-owners: `CELL_OWNER_USER_IDS_JSON` (JSON-array)
- Per-case roller lagres i tabellen `rag_case_access`:
  - `owner`
  - `admin`
  - `viewer`

Når RBAC er aktiv må kall fra Scaffold inneholde:

```http
X-Cell-Gateway-Secret: <secret>
X-Cell-User-Id: <bruker-id>
```

`X-API-Key` (admin) kan brukes som break-glass/bypass.

## Nye API-endepunkter

- `GET /v1/cell/cases`
  - returnerer tilgjengelige RAG-cases + brukerens rolle
- `POST /v1/cell/cases/{case_id}/query`
  - tvunget case query (brukes av RAGQueryCell)
- `GET /v1/cell/cases/{case_id}/corpus`
  - paginert liste over dokumenter/chunks i valgt case
- `GET /v1/cell/cases/{case_id}/links`
  - lenkegraf mellom dokumenter (internal/external/unresolved)
- `GET /v1/cell/cases/{case_id}/documents/{doc_id}/links`
  - lenker for ett dokument
- `GET /v1/cell/cases/{case_id}/members`
  - list medlemmer (`admin`+)
- `PUT /v1/cell/cases/{case_id}/members/{user_id}`
  - sett rolle (owner kreves; owner-rolle kan kun gis via admin key)
- `DELETE /v1/cell/cases/{case_id}/members/{user_id}`
  - fjern rolle (owner kreves)

## Foreslåtte CellScaffold-celler

1. `RAGCaseCatalogCell`
   - kaller `GET /v1/cell/cases`
   - viser hvilke case brukeren har tilgang til

2. `RAGQueryCell`
   - kaller `POST /v1/cell/cases/{case_id}/query`
   - kan bytte `model_profile` per forespørsel

3. `RAGCorpusExplorerCell`
   - kaller `GET /v1/cell/cases/{case_id}/corpus`
   - søk + paginering + filtrering

4. `RAGDocumentLinksCell`
   - kaller `GET /v1/cell/cases/{case_id}/documents/{doc_id}/links`
   - grafnavigering på tvers av dokumenter

5. `RAGCaseMembersAdminCell`
   - kaller members-endepunktene
   - kun tilgjengelig for owner/admin

## Drift

- Kjør migrasjoner:

```bash
python -m scripts.apply_migrations
```

- Verifiser RBAC:

```bash
curl -s http://localhost:8000/v1/cell/cases \
  -H "X-Cell-Gateway-Secret: <secret>" \
  -H "X-Cell-User-Id: <user-id>"
```

- Hvis RBAC skrus av (`CELL_ACCESS_CONTROL_ENABLED=false`) er cell-endepunktene åpne for intern utvikling/testing.
