# Case-bytte for research-klienter

Dette dokumentet beskriver et enkelt klientmønster for research-klienter som bruker `doc.haven.digipomps.org`.

Målet er å redusere feil der klienten starter i ett case, men egentlig burde spurt i et annet.

## Hvorfor dette trengs

Pa `doc.haven.digipomps.org` finnes minst to ulike verktøynivå:

- `dimy_docs` for utviklere og kodeassistenter
- `dimy_prompts` for brukerrettet cellesammensetning og arbeidsrom

Hvis klienten sporrer i feil case, blir svaret lett bredt, svakt eller defensivt.

## Dokumentert signal

`POST /v1/research/query` kan returnere:

- `retrieval_debug.query_plan.case_guidance.level`
- `retrieval_debug.query_plan.case_guidance.message`
- `retrieval_debug.query_plan.case_guidance.suggested_case_id`

Dette skal behandles som et maskinlesbart hint om bedre casevalg.

## Anbefalt klientflyt

1. kall `GET /v1/research/cases`
2. velg et første case ut fra sporsmalet
3. kall `POST /v1/research/query`
4. sjekk `retrieval_debug.query_plan.case_guidance`
5. hvis `suggested_case_id` finnes:
   - rapporter kort at klienten startet i feil case
   - kall `POST /v1/research/query` pa nytt med det foreslatte caset
   - bruk det andre svaret som primart svar

## Praktisk eksempel

Hvis klienten sporrer:

- `Hvordan kan jeg sette sammen celler som komponenter for et arbeidsrom?`

og starter i `dimy_docs`, skal den forvente at svaret kan inneholde:

- et defensivt svar som peker til `dimy_prompts`
- `case_guidance.suggested_case_id = "dimy_prompts"`

Da bor klienten sporre pa nytt i `dimy_prompts` i stedet for a bruke det første svaret som sluttresultat.

## Nar klienten ikke bor bytte case

Klienten bor ikke bytte case bare fordi svaret er kort.

Bytt case nar:
- `suggested_case_id` faktisk finnes
- eller dokumentasjonen eksplisitt sier at sporsmalet horer hjemme i et annet case

Ikke bytt case bare pa grunn av egen gjetning hvis corpus ikke støtter det.
