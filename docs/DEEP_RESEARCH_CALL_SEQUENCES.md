# Deep Research kallsekvenser for `doc.haven.digipomps.org`

Dette dokumentet gir konkrete kallsekvenser for research-klienter som skal bruke `doc.haven.digipomps.org`.

Målet er a redusere feil casevalg og gi en klient en enkel, repeterbar arbeidsflyt.

## Felles start

Start alltid med:

1. `GET /v1/research/cases`
2. velg smaleste relevante case
3. `POST /v1/research/query`
4. hvis `retrieval_debug.query_plan.case_guidance.suggested_case_id` finnes:
   - rapporter kort at forste case var et mismatch
   - gjenta `POST /v1/research/query` i foreslatt case
   - bruk det andre svaret som primart svargrunnlag

## Sekvens A: tekniske sporsmal for utviklere og kodeassistenter

Bruk denne sekvensen nar brukeren spor om:

- API-er
- auth
- kontrakter
- `CellProtocol`
- runtime-adferd
- implementerte celler

Velg case:

- `dimy_docs`

Anbefalt arbeidsflyt:

1. `GET /v1/research/cases`
2. `POST /v1/research/query` mot `dimy_docs`
3. hvis sporsmalet gjelder inventar eller auth:
   - `GET /v1/research/cases/dimy_docs/corpus?q=RAG_SERVICE_API_ENDPUNKTER&limit=10`
   - `GET /v1/research/cases/dimy_docs/corpus?q=DEEP_RESEARCH_API&limit=10`
4. hvis sporsmalet gjelder navigasjon i dokumentasjonen:
   - `GET /v1/research/cases/dimy_docs/links`
   - eventuelt `GET /v1/research/cases/dimy_docs/documents/{doc_id}/links`

Eksempelqueries:

- `Hvilke API-endepunkter finnes i RAG-servicen, og hvilke er admin vs chat vs research?`
- `Hvordan virker case-basert promptvalg i RAG-servicen?`
- `Hvilke dokumenter beskriver CellProtocol-kontrakter og implementerte RAG-celler?`

## Sekvens B: brukerrettet cellesammensetning og arbeidsrom

Bruk denne sekvensen nar brukeren spor om:

- hvordan sette sammen celler
- hvordan bygge et arbeidsrom
- hvilke byggesteiner som passer sammen
- routervalg og dokumenterte oppskrifter

Velg case:

- `dimy_prompts`

Anbefalt arbeidsflyt:

1. `GET /v1/research/cases`
2. `POST /v1/research/query` mot `dimy_prompts`
3. hvis klienten trenger a kontrollere hvilke oppskrifter som finnes:
   - `GET /v1/research/cases/dimy_prompts/corpus?q=WORKSPACE&limit=20`
   - `GET /v1/research/cases/dimy_prompts/corpus?q=CELL_SELECTION_GUIDE&limit=20`
4. hvis klienten vil følge forbindelser mellom guider:
   - `GET /v1/research/cases/dimy_prompts/links`

Eksempelqueries:

- `Hvordan setter jeg sammen et arbeidsrom med katalog, RAG og prompt-admin?`
- `Hvilke dokumenterte celler bor inngaa i et brukerrettet arbeidsrom for dokumentasjon?`
- `Nar bor jeg velge fast case, og nar bor jeg bruke router?`

## Sekvens C: oppdag feil casevalg tidlig

Bruk denne sekvensen nar klienten er usikker pa casevalg.

Anbefalt arbeidsflyt:

1. velg det beste første caset du kan begrunne
2. kall `POST /v1/research/query`
3. sjekk:
   - `retrieval_debug.query_plan.selected_case`
   - `retrieval_debug.query_plan.case_guidance`
4. hvis `case_guidance.suggested_case_id` finnes:
   - kall samme query pa nytt i det foreslatte caset
   - si eksplisitt at klienten byttet case

Praktisk eksempel:

- første kall i `dimy_docs`:
  - `Hvordan kan jeg sette sammen celler som komponenter for et arbeidsrom?`
- forventet respons:
  - `case_guidance.suggested_case_id = "dimy_prompts"`
- nytt kall:
  - samme query i `dimy_prompts`

## Hva klienten ikke bor gjore

- ikke bland `dimy_docs` og `dimy_prompts` i samme første query uten grunnlag i kildene
- ikke anta at prompts er riktig case for API-sporsmal
- ikke anta at docs er riktig case for brukerrettet komposisjon
- ikke overstyr `case_guidance` med egen gjetning uten sterkere dokumentert grunnlag
