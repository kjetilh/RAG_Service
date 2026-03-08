# Deep Research API

Dette dokumentet beskriver et read-only API for dokumentasjon, prompts og andre research-orienterte RAG-cases.

## Formaal

API-et er laget for:

- ChatGPT Deep Research eller tilsvarende research-klienter
- lesing av dokumentasjon og prompts
- oppslag med sitater og lenker
- nedlasting av kildedokumenter

API-et er ikke laget for:

- ingest
- sync
- rolleendringer
- admin-operasjoner

## Autentisering

Research-API-et bruker bearer-token.

Sett `RESEARCH_API_TOKENS_JSON` i miljoet:

```json
{
  "replace-with-long-random-token": {
    "label": "chatgpt-deep-research",
    "scopes": ["research:read", "research:download"],
    "case_ids": ["doc_case", "dimy_docs", "dimy_prompts"]
  }
}
```

Regler:

- `research:read`: tilgang til cases, query, corpus og lenker
- `research:download`: tilgang til kildefilnedlasting
- `case_ids`: valgfri avgrensing til bestemte RAG-cases

Hvis `case_ids` utelates eller er tom, far tokenet lese alle enabled cases.

For nedlastingslenker bor du ogsa sette:

```text
RESEARCH_DOWNLOAD_SIGNING_KEY=<lang tilfeldig hemmelighet>
RESEARCH_DOWNLOAD_TTL_SECONDS=300
```

Da returnerer API-et kortlivede, signerte `download_url`-lenker i stedet for a eksponere tokenet i query string.

I VPS compose-oppsettet brukes disse service-spesifikke variablene:

- `RAG_INNOVASJON_RESEARCH_API_TOKENS_JSON`
- `RAG_INNOVASJON_RESEARCH_DOWNLOAD_SIGNING_KEY`
- `RAG_INNOVASJON_RESEARCH_DOWNLOAD_TTL_SECONDS`
- `RAG_DIMY_RESEARCH_API_TOKENS_JSON`
- `RAG_DIMY_RESEARCH_DOWNLOAD_SIGNING_KEY`
- `RAG_DIMY_RESEARCH_DOWNLOAD_TTL_SECONDS`

## Headers

Vanlig bruk:

```http
Authorization: Bearer <token>
```

For direkte browser-klikk pa `download_url` brukes normalt en kortlivet signert lenke:

- `exp`: utlopstid
- `cases`: signert case-scope
- `sig`: HMAC-signatur

Hvis `RESEARCH_DOWNLOAD_SIGNING_KEY` ikke er satt, faller API-et midlertidig tilbake til `access_token` i query string for bakoverkompatibilitet. Det bor bare brukes som overgang.

## Endepunkter

### `GET /v1/research/cases`

Lister enabled cases tokenet har lov til a lese.

### `POST /v1/research/query`

Request:

```json
{
  "case_id": "dimy_docs",
  "query": "Hvordan virker RAG gateway i scaffold?",
  "top_k": 8,
  "model_profile": "gpt-4o-mini"
}
```

Respons:

- `answer`
- `citations`
- `retrieval_debug`
- `trace`

Hvis tokenet har `research:download`, blir `citation.download_url` satt til et research-beskyttet download-endepunkt.

### `GET /v1/research/cases/{case_id}/corpus`

Query-parametre:

- `q`
- `limit`
- `offset`
- `include_tombstones`

### `GET /v1/research/cases/{case_id}/links`

Returnerer linkgraph for hele caset.

### `GET /v1/research/cases/{case_id}/documents/{doc_id}/links`

Returnerer linkgraph for ett dokument.

### `GET /v1/research/documents/{doc_id}/download`

Krever enten:

- `Authorization: Bearer <token>` med `research:download`
- eller en gyldig signert nedlastingslenke fra `download_url`

## Sikkerhetsnotater

- Dette API-et er separat fra celle-gatewayen og deler ikke `X-Cell-Gateway-Secret`.
- Ikke bruk `X-API-Key` for Deep Research.
- Signerte nedlastingslenker er bevisst kapabilitetsbaserte og kortlivede. De er tryggere enn a lekke bearer-token i URL-er, men de er fortsatt delbare til de utloper.
- Dagens eldre `/v1/documents/{doc_id}/download` finnes fortsatt for eksisterende klienter. For ny research-bruk bor `/v1/research/...` foretrekkes.

## Case-strategi

For dokumentasjon og prompts bor research-klienter holde disse som separate cases:

1. dokumentasjon
   - kodebruk
   - arkitektur
   - driftsdokumentasjon
2. prompts
   - systeminstruksjoner
   - promptmaler
   - beslutninger om svarstil og guardrails

Start med `GET /v1/research/cases`, velg smaleste relevante case, og kryss bare over til links/corpus i andre cases hvis sporsmalet faktisk krever det.

## Anbefalt oppsett

For dokumentasjon og prompts anbefales minst to tokens:

1. `chatgpt-deep-research-docs`
   - scopes: `research:read`, `research:download`
   - case_ids: dokumentasjons- og promptcases
2. `browser-research-readonly`
   - scopes: `research:read`
   - case_ids: samme eller smalere

Da kan den ene brukes til full research med kildevisning, mens den andre ikke kan laste ned filer.
