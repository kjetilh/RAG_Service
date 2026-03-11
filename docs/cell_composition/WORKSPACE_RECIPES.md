# Arbeidsromsoppskrifter for dokumenterte RAG-celler

Dette dokumentet samler noen enkle oppskrifter for hvordan RAG-relaterte celler kan settes sammen i et arbeidsrom.

Oppskriftene holder seg til det som faktisk er dokumentert i denne repoen:
- `docs/CELLS_EMBEDDING.md`
- `docs/SCAFFOLD_CELL_PROMPTS.md`

Hvis du trenger et oppsett som går utover dette, må det dokumenteres først.

## 1. Les og spør i ett case

Bruk dette når brukeren først og fremst vil lese, spørre og følge opp svar i ett kjent kunnskapsdomene.

Dokumenterte byggesteiner:
- `RAGCaseCatalogCell`
- `RAGQueryCell`
- `RAGCorpusExplorerCell`

Praktisk oppsett:
1. La brukeren velge case i `RAGCaseCatalogCell`.
2. Bruk `RAGQueryCell` som hovedflate for spørsmål.
3. Legg `RAGCorpusExplorerCell` ved siden av for å se hvilke dokumenter som faktisk ligger i caset.

Hvorfor dette fungerer:
- brukeren får både svar og innsyn i corpus
- arbeidsrommet holder seg enkelt

Hva du ikke skal anta:
- at dette alene gir lenkenavigasjon mellom dokumenter
- at alle case trenger admin-funksjoner

## 2. Sporbar dokumentutforskning

Bruk dette når brukeren må kunne kontrollere kildene og følge dokumentlenker videre.

Dokumenterte byggesteiner:
- `RAGQueryCell`
- `RAGCorpusExplorerCell`
- `RAGDocumentLinksCell`

Praktisk oppsett:
1. Start i `RAGQueryCell` for å finne relevante dokumenter.
2. Bruk `RAGCorpusExplorerCell` for å se dokumentene i caset.
3. Åpne `RAGDocumentLinksCell` når brukeren vil følge henvisninger eller se uløste lenker.

Hvorfor dette fungerer:
- det gir et tydelig skille mellom svar, corpus og lenkegraf
- det er bedre egnet for kildekritisk arbeid enn et rent chat-oppsett

Hva du ikke skal anta:
- at lenkegrafen automatisk løser manglende dokumentasjon

## 3. Delt arbeidsrom med tilgangsstyring

Bruk dette når flere skal jobbe mot samme case, men ikke ha samme rolle.

Dokumenterte byggesteiner:
- `RAGCaseCatalogCell`
- `RAGQueryCell`
- `RAGCaseMembersAdminCell`

Praktisk oppsett:
1. Bruk `RAGCaseCatalogCell` for å vise hvilke case som finnes.
2. Bruk `RAGQueryCell` som vanlig arbeidsflate.
3. Gi eier eller admin tilgang til `RAGCaseMembersAdminCell` for medlemsstyring.

Hvorfor dette fungerer:
- medlemsstyring holdes adskilt fra vanlig spørrearbeid
- samme arbeidsrom kan brukes av både lesere og administratorer

Hva du ikke skal anta:
- at alle brukere skal se admin-cellen

## 4. Router-oppskrift for flere domener

Bruk dette når arbeidsrommet skal velge mellom flere RAG-domener.

Dokumenterte byggesteiner:
- router-celle
- RAG-kall-celle

Praktisk oppsett:
1. router-cellen velger domene, modellprofil og `source_type`.
2. RAG-kall-cellen sender meldingen til riktig endpoint.
3. Bruk hardkodet innovasjon-celle eller DiMy-celle bare når arbeidsrommet skal være låst til ett domene.

Hvorfor dette fungerer:
- brukeren slipper å kjenne tjenestestrukturen
- samme arbeidsrom kan håndtere flere typer spørsmål

Hva du ikke skal anta:
- at routeren alltid er bedre enn et enkelt, fast case
- at flere domener betyr at alle spørsmål bør blandes i samme svar

## Hvordan velge riktig oppskrift

Velg den enkleste dokumenterte oppskriften som dekker behovet:
- kjent case og raske svar: oppskrift 1
- behov for sporbarhet og lenker: oppskrift 2
- delt case med styring: oppskrift 3
- flere domener eller modellprofiler: oppskrift 4
