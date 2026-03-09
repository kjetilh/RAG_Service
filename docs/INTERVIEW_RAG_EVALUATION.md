# Interview-RAG for Innovasjonsledelse: Muligheter og anbefalt retning

## 1) Hva vi allerede har (kan brukes direkte)

Dagens `rag_service` har allerede fundamentet for en intervju-løsning:

- Multi-case konfig via `config/rag_cases.yml` (strict validering).
- Deterministisk planner + trace (`/v1/query` med `trace`).
- Per-case tilgangskontroll for CellScaffold (`/v1/cell/cases/*`).
- Sync-orchestrator for løpende dokumentoppdatering.
- Kildebarhet (citations) og streng instruks om å ikke finne på innhold.
- Modellprofiler (`model_profile`) for bytte av språkmodell per kall.

Begrensning i dagens løsning:

- Ingen dedikert aggregat-endepunkt som beregner "kollektiv mening per fast spørsmål".
- Ingen eksplisitt spørsmålskatalog som first-class datastruktur.
- Ingen eksplisitt konflikt-/enighetsindikator på tvers av intervjuer (må i dag løses i prompt).

## 2) Anbefalt målarkitektur

### 2.1 Domenesplitt

Bruk en dedikert RAG-case (eller dedikert instans) for intervjuene:

- Case-ID: `innovasjon_intervjuer`
- Source type: `innovasjon_intervju_transcript`

Anbefaling:

- Hvis dette er et separat arbeidsløp med sensitivt materiale: egen RAG-instans.
- Hvis dette er lavere risiko og du vil minimere drift: ny case i eksisterende innovasjons-RAG.

### 2.2 Struktur på transkripsjoner (kritisk)

For å få stabile resultater per spørsmål må transkripsjoner ha fast format.

Minimumsformat i Markdown:

- Header-metadata (intervju-id, dato, rolle, sektor).
- En seksjon per spørsmål med fast nøkkel:
  - `## Q1: <spørsmålstekst>`
  - `## Q2: ...`
- Informantens svar under hver Q-seksjon.

Hvorfor dette virker i dagens stack:

- Chunker splitter på Markdown-headings.
- Hvert spørsmål blir tydelig semantisk segment for retrieval.

### 2.3 Aggregasjonslag over RAG

Innfør et nytt lag (API/celle) for "spørsmålsmatrise":

- Input: fast spørsmålskatalog + case_id.
- For hvert spørsmål:
  - Kjør RAG-kall med case-filter.
  - Krev strukturert output:
    - `hovedtrekk`
    - `enighet`
    - `uenighet`
    - `styrke_på_grunnlag` (høy/middels/lav)
    - `hva_mangler_i_dokumentasjon`
    - `kilder`
- Returner samlet JSON for alle spørsmål.

Dette gir et stabilt arbeidsprodukt for bokprosjektet og kan vises direkte i CellScaffold.

## 3) Foreslått implementasjonsløp (inkrementelt)

### Fase A (rask verdi, lav risiko)

1. Opprett ny case i `config/rag_cases.yml` for intervjuer.
2. Definer ny promptprofil for intervju-syntese (saklig, kildebundet, ingen hallusinasjon).
3. Last inn transkripsjoner med `source_type=innovasjon_intervju_transcript`.
4. Bruk `/v1/query` med `case_id=innovasjon_intervjuer`.

Resultat:

- Du får spørsmål-svar med kilder umiddelbart.
- God nok for pilot med manuell oppfølging.

### Fase B (det du faktisk trenger for "kollektiv mening")

1. Legg til spørsmålskatalog (f.eks. `config/interview_questions.yml`).
2. Legg til nytt API:
   - `POST /v1/interviews/collective-summary`
3. Legg til cell-endepunkt:
   - `POST /v1/cell/cases/{case_id}/interviews/collective-summary`
4. Legg til eksport:
   - JSON + Markdown rapport per kjøring.

Resultat:

- Reproduserbar "matrise per spørsmål" uten manuell prompting.

### Fase C (kvalitetssikring og forbedringssløyfe)

1. Mål dekning per spørsmål:
   - antall intervjuer med evidens
   - antall unike kilder brukt
2. Flagging:
   - "svakt grunnlag"
   - "inkonsistent grunnlag"
3. Vis forbedringsforslag:
   - hvilke spørsmål mangler dekning
   - hvilke transkripsjoner bør etterkodes/struktureres bedre

## 4) Cell-perspektiv (neste steg i Scaffold)

Anbefalte celler:

- `InterviewQuestionMatrixCell`:
  - viser kollektiv mening per spørsmål.
- `InterviewEvidenceCell`:
  - drilldown til kilder/citater per spørsmål.
- `InterviewCoverageCell`:
  - viser hvilke spørsmål som har svak dekning.
- `InterviewAdminCell`:
  - trigger sync/reingest og promptversjonering.

Rollemodell:

- owner/admin: kjøre sync, endre promptprofil, oppdatere spørsmålskatalog.
- viewer: lese matrise, gjøre oppslag.

## 5) Risikoer og tiltak

- Risiko: Ustrukturert transkripsjon gir ustabil spørsmålsanalyse.
  - Tiltak: innfør enkel transkripsjonsmal med faste `Q1..Qn` headings.
- Risiko: For brede spørsmål gir "grå" svar.
  - Tiltak: one-question-per-run i aggregasjonslaget.
- Risiko: Hallusinasjon ved lav dekning.
  - Tiltak: streng prompt + eksplisitt "ikke dokumentert" + coverage score.

## 6) Anbefaling (kort)

Bygg dette som en ny intervju-case først (Fase A), og legg deretter til et eksplisitt kollektivt spørsmåls-endepunkt (Fase B).  
Det gir rask verdi nå, og en robust, cellevennlig løsning for videreutvikling.
