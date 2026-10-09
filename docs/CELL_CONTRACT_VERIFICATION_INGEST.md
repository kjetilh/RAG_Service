# Cell Contract Verification Ingest

Dette dokumentet beskriver hvordan `ContractProbeVerificationRecord` fra `CellProtocol` pushes inn i `rag_service` som et vanlig dokument med chunkede verifikasjonsresultater.

## Endepunkt

- `POST /v1/cell/cases/{case_id}/contract-verification`
- autentisering: `X-Cell-Gateway-Secret` + `X-Cell-User-Id` eller `X-API-Key`
- autorisasjon: `admin`-rolle på caset

## Formål

Bruk endepunktet når en celle allerede er probet i runtime og resultatet skal gjøres søkbart for:

- AI-kodeassistenter
- menneskelige utviklere
- dokumentasjonsaudit
- stale-detection mellom deklarert kontrakt og sist verifisert runtime-oppførsel

Dette er ikke et query-endepunkt. Det er et ingest-endepunkt for verifiserte kontraktartefakter.

## Forventet payload

Payloaden følger `ContractProbeVerificationRecord`-shape fra `CellProtocol` og bruker camelCase-felter. Viktige felter:

- `repo`
- `cellType`
- `targetEndpoint`
- `targetLabel`
- `verificationStatus`
- `lastVerifiedAt`
- `contractVersion`
- `failedAssertionCount`
- `sourceType`
- `recordMarkdown`
- `chunks`

Hver chunk bør minst inneholde:

- `id`
- `documentKind`
- `content`

Valgfrie chunk-felter som brukes til filtrering og bedre seksjonsstier:

- `key`
- `phase`
- `status`
- `verifiedAt`

## Chunk-typer

Disse chunk-typene er forventet fra `CellProtocol` sin eksport:

- `summary`
- `key_contract`
- `failed_assertion`
- `flow_assertion_group`

Hvis `chunks` er tom, brukes `recordMarkdown` som fallback til ett `summary`-chunk. Hvis begge mangler returneres `400`.

## Lagringsmodell

Ved ingest gjør tjenesten dette:

1. bygger en stabil `doc_id` basert på `repo` + `targetEndpoint`
2. upserter dokumentmetadata i `documents`
3. sletter gamle chunks for samme dokument
4. skriver inn nye chunks med stabile `chunk_id`-er
5. regenererer embeddings for alle chunks
6. markerer dokumentet som `active` og oppdaterer `updated_at`

Dette gjør at samme celle-endepunkt oppdateres inkrementelt i stedet for å dupliseres ved hver probe-kjøring.

## Source type og case-filter

`sourceType` må være tillatt for caset i `config/rag_cases.yml`. For dokumentasjons-RAG er typisk verdi:

- `cellprotocol_docs`

Hvis caset ikke tillater oppgitt `sourceType`, returnerer API-et `400`.

## Praktisk bruk

Typisk flyt:

1. `ContractProbeCell` kjører mot en mål-celle i runtime eller staging
2. `CellProtocol` eksporterer `exploreContractVerificationRecord(...)` eller `exploreContractVerificationChunks(...)`
3. en ingest-celle eller CI-klient sender recorden til `rag_service`
4. dokumentet blir søkbart via vanlige `query`/`corpus`-endepunkter

## Anbefalt bruk i CellScaffold

Hvis dette skal eksponeres som vanlig celleintegrasjon, lag en dedikert `RAGContractVerificationIngestCell` som:

- validerer at `sourceType` matcher valgt case
- sender ferdig `ContractProbeVerificationRecord` uten lokal omskriving
- returnerer `doc_id`, `title`, `source_type` og `chunk_count`
- kan brukes både fra manuell debugging og fra agentdrevne verifikasjonsløp
