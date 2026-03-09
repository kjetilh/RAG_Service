# ChatGPT Deep Research Prompt: Interview-RAG for kollektiv mening

## Rolle

Du er Principal Research Engineer for Retrieval-Augmented Systems i en norsk produktkontekst (HAVEN/CellScaffold).

## Mål

Design en robust metode for å analysere lederintervjuer med fast spørsmålssett, slik at vi får:

1. Hovedtrekk per intervju.
2. Kollektiv mening per spørsmål (på tvers av intervjuer).
3. Tydelig markering av enighet, uenighet, svak dekning og dokumentasjonsgap.
4. En løsning som passer inn i en eksisterende RAG-tjeneste + CellScaffold-celler.

## Eksisterende system (må tas hensyn til)

- FastAPI-basert RAG med:
  - `POST /v1/query` (case-aware)
  - deterministisk planner og trace
  - kildehenvisninger (citations)
  - per-case tilgang via `/v1/cell/cases/*`
  - sync-orchestrator for dokumentkilder
  - bytte av modellprofil per request (`model_profile`)
- Dokumentchunking skjer med markdown-headings.
- Vi ønsker å laste opp transkripsjoner og jobbe case-spesifikt.

## Spørsmål som skal besvares

1. Hva er beste praksis for å strukturere transkripsjoner for stabil "per-question retrieval"?
2. Hvilken arkitektur er best for "collective meaning per question"?
   - ren RAG prompting
   - RAG + strukturert ekstraksjon (JSON schema)
   - RAG + egen analytisk lagring (spørsmål/svar-matrise)
3. Hvordan bør konflikt/enighet kvantifiseres uten å miste sporbarhet til kilder?
4. Hvordan kan vi unngå hallusinasjon når datagrunnlaget er svakt?
5. Hvilke evalueringsmetoder anbefales for denne typen kvalitativ analyse?
6. Hvordan designe dette slik at nye domener/cases kan opprettes med minimal kode?
7. Hvilke API-er og celletyper bør vi implementere i CellScaffold?

## Leveranseformat

Gi svaret i følgende struktur:

1. **Executive Summary** (maks 15 linjer)
2. **Target Architecture** (komponentdiagram i tekst + dataflyt)
3. **Data Contract**
   - foreslått transkripsjonsformat
   - spørsmålskatalog-format
   - output JSON schema for kollektivt sammendrag
4. **Algorithm**
   - steg-for-steg for per-spørsmål aggregasjon
   - hvordan beregne confidence/dekning/uenighet
5. **API Design**
   - konkrete endpoint-forslag med request/response
6. **Cell Design**
   - foreslåtte celler for matrise, drilldown, admin
7. **Evaluation Plan**
   - metrikk, testsett, akseptansekriterier
8. **Risk Register**
   - topp 10 risikoer med avbøtende tiltak
9. **Incremental Rollout Plan**
   - Phase A/B/C med estimat og avhengigheter
10. **References**
   - prioriter primærkilder/metodikk med lenker

## Kvalitetskrav

- Ingen løse antagelser uten å markere dem eksplisitt.
- Tydelig skille mellom:
  - anbefalt praksis
  - valgfri forbedring
  - eksperimentell idé
- Alltid inkluder:
  - hvordan vi bevarer sporbarhet fra syntese -> sitat -> dokument.
  - hvordan vi håndterer "ikke nok data" uten å finne på noe.

## Kontekstvalg

Språk i output: Norsk (Bokmål), med tekniske begreper på engelsk der det er standard.
