# Deep Research API

Dette dokumentet beskriver et read-only API for dokumentasjon, prompts og andre research-orienterte RAG-cases.

For full route-inventar pa tvers av `chat`, `admin`, `cell`, `interviews` og `research`, se `docs/RAG_SERVICE_API_ENDPUNKTER.md`.

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
    "case_ids": ["dimy_docs"]
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

Research-endepunktene er:

- `GET /v1/research/cases`
- `POST /v1/research/query`
- `GET /v1/research/cases/{case_id}/corpus`
- `GET /v1/research/cases/{case_id}/links`
- `GET /v1/research/cases/{case_id}/documents/{doc_id}/links`
- `GET /v1/research/documents/{doc_id}/download`

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

Hvis klienten spurte i et case som ser feil ut for sporsmalet, kan `retrieval_debug.query_plan.case_guidance` returnere:

- `level`
- `message`
- `suggested_case_id`

Det er et signal om at klienten bor sporre pa nytt i et annet case i stedet for a stole pa et bredt eller svakt svar fra feil corpus.

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

Anbefalt target-arkitektur er a holde dokumentasjon og prompts som separate cases.

Status i dette repoet akkurat na:

- `config/rag_cases.yml` definerer `dimy_docs` og `dimy_prompts` pa `doc`-siden
- `dimy_docs` er utvikler- og kodeassistentcaset for `CellProtocol`, implementerte celler, API-er og teknisk dokumentasjon
- `dimy_prompts` er brukerrettet caset for cellesammensetning, arbeidsrom, byggesteiner og dokumenterte oppskrifter

Det betyr at research-klienter pa `doc.haven.digipomps.org` bor velge case eksplisitt ut fra sporsmalstype:

1. `dimy_docs`
   - kodebruk
   - arkitektur
   - driftsdokumentasjon
   - API-er, kontrakter og runtime-adferd
2. `dimy_prompts`
   - arbeidsrom
   - cellesammensetning
   - byggesteiner og routervalg
   - dokumenterte oppskrifter for brukere

Start med `GET /v1/research/cases`, velg smaleste relevante case, og kryss bare over til links/corpus i andre cases hvis sporsmalet faktisk krever det.

### Praktisk valg pa `doc.haven.digipomps.org`

Velg `dimy_docs` nar sporsmalet handler om:

- `CellProtocol`
- implementerte celler
- API-endepunkter
- auth
- kontrakter
- runtime-adferd
- tekniske begrensninger

Velg `dimy_prompts` nar sporsmalet handler om:

- hvordan sette sammen celler
- hvordan bygge et arbeidsrom
- hvilke byggesteiner som passer sammen
- routervalg og komposisjonsoppskrifter

Hvis en research-klient starter i feil case, bor den si det eksplisitt og bytte case i stedet for a svare bredt fra feil corpus.

### Anbefalt klientmønster

For research-klienter som skal velge case automatisk:

1. kall `GET /v1/research/cases`
2. velg beste case ut fra sporsmalet
3. kall `POST /v1/research/query`
4. hvis `retrieval_debug.query_plan.case_guidance.suggested_case_id` finnes:
   - rapporter kort at forste case var et mismatch
   - kall `POST /v1/research/query` pa nytt med det foreslatte caset
   - bruk det andre svaret som primart svargrunnlag

Dette er spesielt nyttig pa `doc.haven.digipomps.org`, der:

- `dimy_docs` dekker utvikler- og kodeassistentsporsmal
- `dimy_prompts` dekker brukerrettet cellesammensetning og arbeidsrom

Se ogsa `docs/DEEP_RESEARCH_CALL_SEQUENCES.md` for konkrete kallsekvenser og eksempelqueries.

### Eksempler

Bruk `dimy_docs` for:

- `Hvilke API-endepunkter finnes i RAG-servicen, og hvilke er admin vs chat vs research?`
- `Hvordan virker CellProtocol-kontrakter og case-basert promptvalg?`

Bruk `dimy_prompts` for:

- `Hvordan setter jeg sammen et arbeidsrom med katalog, RAG og prompt-admin?`
- `Hvilke celler bor inngaa i et brukerrettet scaffold for dokumentasjonsarbeid?`

## Anbefalt oppsett

For dokumentasjon og prompts anbefales minst to tokens:

1. `chatgpt-deep-research-docs`
   - scopes: `research:read`, `research:download`
   - case_ids: dokumentasjons- og promptcases
2. `browser-research-readonly`
   - scopes: `research:read`
   - case_ids: samme eller smalere

Da kan den ene brukes til full research med kildevisning, mens den andre ikke kan laste ned filer.
