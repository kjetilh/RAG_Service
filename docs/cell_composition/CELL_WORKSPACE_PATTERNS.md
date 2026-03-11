# Arbeidsromsmønstre for RAG-celler

Dette dokumentet beskriver en liten, dokumentert kjerne av mønstre for å sette sammen RAG-relaterte celler i et arbeidsrom.

Grunnlaget her er dokumentasjonen i denne repoen, særlig:
- `docs/CELLS_EMBEDDING.md`
- `docs/SCAFFOLD_CELL_PROMPTS.md`

Hvis et oppsett eller en celle ikke er nevnt der, skal det ikke presenteres som dokumentert.

## 1. Enkel spørreflate

Bruk dette når målet er å spørre én RAG-case og få et svar raskt.

Dokumenterte byggesteiner:
- `RAGCaseCatalogCell`
- `RAGQueryCell`

Hvordan det brukes:
1. `RAGCaseCatalogCell` viser hvilke case brukeren har tilgang til.
2. `RAGQueryCell` sender spørringen til valgt case.

Når dette mønsteret passer:
- brukeren vet omtrent hva de vil spørre om
- det viktigste er rask tilgang til svar, ikke corpus-utforskning

Begrensning:
- dette mønsteret gir ikke i seg selv navigasjon i dokumentlenker eller dyp corpus-utforskning

## 2. Utforsk dokumentasjon og kilder

Bruk dette når målet er å forstå hva som finnes i corpus og følge lenker mellom dokumenter.

Dokumenterte byggesteiner:
- `RAGQueryCell`
- `RAGCorpusExplorerCell`
- `RAGDocumentLinksCell`

Hvordan det brukes:
1. `RAGQueryCell` finner relevante dokumenter og chunks.
2. `RAGCorpusExplorerCell` lar brukeren søke og bla i corpus.
3. `RAGDocumentLinksCell` brukes når man vil følge lenker fra ett dokument til andre dokumenter.

Når dette mønsteret passer:
- brukeren trenger sporbarhet
- brukeren vil kontrollere kildene før svaret brukes videre
- dokumentasjonen er spredt over flere filer

Begrensning:
- dette krever mer aktiv navigasjon enn en ren spørreflate

## 3. Tilgangsstyrt arbeidsrom

Bruk dette når flere personer deler samme RAG-case, men ikke skal ha samme rettigheter.

Dokumenterte byggesteiner:
- `RAGCaseCatalogCell`
- `RAGQueryCell`
- `RAGCaseMembersAdminCell`

Hvordan det brukes:
1. `RAGCaseCatalogCell` brukes for å finne tilgjengelige case.
2. `RAGQueryCell` brukes i den daglige arbeidsflyten.
3. `RAGCaseMembersAdminCell` brukes når eier eller admin må styre hvem som har tilgang.

Når dette mønsteret passer:
- et case deles mellom flere brukere
- noen skal bare lese, mens andre skal administrere tilgang

Begrensning:
- dette mønsteret handler om tilgang og styring, ikke om innholdsproduksjon

## 4. Router-basert oppsett

Bruk dette når arbeidsrommet skal velge mellom flere RAG-domener eller modellprofiler.

Dokumenterte byggesteiner fra promptdokumentasjonen:
- en router-celle som velger domene og modellprofil
- en RAG-kall-celle som sender forespørselen til riktig endpoint

Hvordan det brukes:
1. router-cellen bestemmer domene, modellprofil og relevante `source_type`-filtre
2. RAG-kall-cellen sender forespørselen videre til riktig tjeneste

Når dette mønsteret passer:
- brukeren skal slippe å velge tjeneste manuelt
- samme arbeidsrom skal kunne spørre flere kunnskapsdomener

Begrensning:
- dokumentasjonen beskriver mønsteret, men ikke et komplett ferdig brukerarbeidsrom

## Hvordan velge mønster

Velg det enkleste dokumenterte oppsettet som dekker behovet:
- bare spørsmål: start med `RAGCaseCatalogCell` + `RAGQueryCell`
- spørsmål pluss kildearbeid: legg til `RAGCorpusExplorerCell` og `RAGDocumentLinksCell`
- delt arbeidsrom med styring: legg til `RAGCaseMembersAdminCell`
- flere domener eller modellprofiler: bruk router-mønsteret

## Hva dokumentasjonen ikke dekker godt nok ennå

Dette er ikke godt nok dokumentert i kildene:
- komplette, ferdige brukerarbeidsrom med skjermflyt
- standardoppsett for ikke-tekniske brukere
- et fullstendig katalogkart over alle implementerte celler utenfor RAG-delen
