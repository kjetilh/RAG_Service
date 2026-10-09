# Status: RAG -> CellProtocol / CellConfiguration

Denne filen oppsummerer hvor vi faktisk er, hva som allerede er levert, og hva som fortsatt mangler for a gjore RAG-funksjonalitet tilgjengelig som celler via `CellConfiguration` og skeleton.

## Status na

Per na er `rag_service` lenger fremme enn integrasjonen mot `CellProtocol`.

Ferdig og committed i `rag_service`:

- PR1: `doc_state` + versjonering i indeks/schema
- PR2: strict `rag_cases.yml` loader
- PR3: deterministisk planner med stabil trace
- PR4: tombstone-basert sync med anti-thrash
- PR5: evaluation gate runner
- PR6: `POST /v1/query` med bakoverkompatibel `chat`-shim
- cell-RBAC og case-endepunkter for:
  - `GET /v1/cell/cases`
  - `POST /v1/cell/cases/{case_id}/query`
  - `GET /v1/cell/cases/{case_id}/corpus`
  - `GET /v1/cell/cases/{case_id}/links`
  - `GET /v1/cell/cases/{case_id}/documents/{doc_id}/links`
  - members admin-endepunkter

Implementert lokalt i `rag_service`, men fortsatt ucommitted:

- intervju-case i `config/rag_cases.yml`
- `POST /v1/interviews/collective-summary`
- `POST /v1/cell/cases/{case_id}/interviews/collective-summary`
- tilhorende tester og runbook-dokumentasjon

Status i `CellScaffold`:

- det finnes en fungerende web/proxy-MVP i `VaporRAGMVP`
- case-listing, query, corpus, links og interview-matrix er lagt til lokalt
- repoet har samtidig mange andre auth-endringer i arbeidskopien, sa RAG-integrasjonen er ikke isolert som en ren, liten leveranse ennå

Status i `CellProtocol`:

- primitive byggesteiner finnes allerede:
  - `CellConfiguration`
  - `CellReference`
  - `setKeysAndValues`
  - skeleton med `Text`, `TextField`, `TextArea`, `Button`, `List`, `Section`, `ScrollView`
- det finnes ikke en standardisert RAG-kontrakt eller en generell RAG-celle i protokollen

## Hva dette betyr

Konklusjonen er at vi ikke bor flytte selve RAG-motoren inn i `CellProtocol`.

Det riktige skillet er:

- `rag_service` eier ingest, indeks, retrieval, planner, sync, sitater og domene-case-konfig
- `CellScaffold` eier runtime-adapteren som eksponerer RAG som en celle og proxier mot `rag_service`
- `CellProtocol` eier den generelle kontrakten som gjor at en RAG-celle kan beskrives og rendres via `CellConfiguration` + skeleton

Det er altsa kontrakten som bor inn i `CellProtocol`, ikke backend-implementasjonen.

## Anbefalt malbilde

Forste produksjonsniva bor vaere:

1. `rag_service` beholdes som ekstern tjeneste.
2. `CellScaffold` far en lokal `RAGGatewayCell` eller `RAGCaseCell`.
3. `CellConfiguration` peker pa den lokale cellen via `cell:///...`.
4. Skeleton brukes til a bygge:
   - case-velger
   - query-visning
   - corpus explorer
   - dokument-lenker
   - interview question matrix
   - case-members admin

Dette kan bygges uten a endre grunnleggende serialisering i `CellProtocol`.

## Foreslatt kontrakt for forste iterasjon

En enkel kontrakt er bedre enn a introdusere mange nye typer for tidlig.

Foreslatt celle-endepunkt:

- `cell:///RAGGateway`

Foreslatte keypaths:

- `cases.list`
- `query.run`
- `corpus.list`
- `links.case`
- `links.document`
- `interviews.collectiveSummary`
- `members.list`
- `members.setRole`
- `members.removeRole`

Foreslatte state-keypaths:

- `state.cases`
- `state.currentCase`
- `state.queryInput`
- `state.queryResult`
- `state.corpus`
- `state.links`
- `state.members`
- `state.lastError`

Payload-format bor vaere objektbasert og deterministisk:

- `query.run`: `{ case_id, message, model_profile?, filters?, top_k? }`
- `corpus.list`: `{ case_id, q?, limit?, offset?, include_tombstones? }`
- `links.document`: `{ case_id, doc_id }`
- `interviews.collectiveSummary`: `{ case_id, question_set_path?, question_set_id?, questions_inline? }`
- `members.setRole`: `{ case_id, user_id, role }`

## Leveransegap akkurat na

Det som mangler for a kunne si at RAG er tilgjengelig via `CellConfiguration` med skeleton er:

1. En stabil kontrakt for RAG-cellen i Cell-landet.
2. En eller flere faktiske celler i `CellScaffold` som eksponerer denne kontrakten.
3. `CellConfiguration`-fabrikker som lager ferdige konfigurasjoner for:
   - query
   - corpus explorer
   - link explorer
   - interview matrix
   - members admin
4. Katalogoppforing i `ConfigurationCatalogCell`.
5. Smoke-tester som viser at en innlogget bruker kan laste en RAG-konfigurasjon og bruke den uten spesialkodet web-side.

## Borde vi bruke ChatGPT Pro na?

Ja, men pa riktig niva.

Verdifull bruk:

- ekstern arkitekturreview av kontrakten mellom `rag_service`, `CellScaffold` og `CellProtocol`
- vurdering av om vi bor ha en `RAGGatewayCell` eller flere spesialiserte celler
- forslag til minimal diff-plan per repo
- testing av om planen er tydelig nok til at en annen agent kunne implementert den

Lite verdifull bruk akkurat na:

- ny migrasjonsskript for database
- ny planner- eller sync-arkitektur for `rag_service`
- generell RAG-teori uten repo-spesifikk kontekst

Med andre ord: bruk ChatGPT som second opinion pa integrasjonsdesign, ikke som erstatning for lokal statuslesing.

## Anbefalt neste arbeidsrekkefolge

1. Commit intervju-endringene i `rag_service` som en separat, ren leveranse.
2. Skriv en kontrakt-spec for `RAGGatewayCell` med keypaths, payloads, state og feilsvar.
3. Implementer `RAGGatewayCell` i `CellScaffold` bak dagens proxylogikk.
4. Legg til `CellConfiguration`-fabrikker + skeleton for query, corpus, links og interviews.
5. Registrer disse i `ConfigurationCatalogCell`.
6. Test en ende-til-ende flyt der en bruker laster en RAG-konfigurasjon fra katalogen og bruker den uten `rag-mvp`-spesialside.
7. Flytt eventuelle generelle hjelpeabstraksjoner opp i `CellProtocol` bare hvis de viser seg a vaere reelt gjenbrukbare.

## Beslutning

Arbeid videre kontrakt-forst.

Ikke start med a flytte RAG-implementasjon inn i `CellProtocol`.
Start med a gjore RAG tilgjengelig gjennom en stabil cellekontrakt som kan beskrives med eksisterende `CellConfiguration`- og skeleton-primitiver.
