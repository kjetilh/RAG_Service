# Valg av RAG-celler etter behov

Dette dokumentet er laget for spørringer som handler om hvilken celle som bør brukes til hva.

Kildene i denne repoen beskriver først og fremst RAG-relaterte celler og RAG-kallsmønstre. Guiden under holder seg derfor til det som faktisk er dokumentert.

## Når brukeren vil spørre dokumentasjonen

Velg:
- `RAGQueryCell`

Bruk den når:
- brukeren skal sende et spørsmål til et bestemt case
- arbeidsrommet allerede vet hvilket case som skal brukes

Se også:
- `RAGCaseCatalogCell` hvis brukeren først må velge case

## Når brukeren må velge eller oppdage riktig case

Velg:
- `RAGCaseCatalogCell`

Bruk den når:
- brukeren ikke vet hvilket case som er relevant
- arbeidsrommet skal vise hvilke case brukeren faktisk har tilgang til

Kombiner typisk med:
- `RAGQueryCell`

## Når brukeren må utforske hele corpus

Velg:
- `RAGCorpusExplorerCell`

Bruk den når:
- brukeren trenger søk og paginering i dokumentene
- svar alene ikke er nok

Kombiner typisk med:
- `RAGQueryCell`
- `RAGDocumentLinksCell`

## Når brukeren må følge lenker mellom dokumenter

Velg:
- `RAGDocumentLinksCell`

Bruk den når:
- dokumentasjon peker videre til andre dokumenter
- man vil se interne, eksterne eller uløste lenker

Kombiner typisk med:
- `RAGCorpusExplorerCell`

## Når arbeidsrommet skal styre tilgang per case

Velg:
- `RAGCaseMembersAdminCell`

Bruk den når:
- en eier eller admin må gi eller fjerne tilgang
- flere brukere deler samme case

Ikke bruk den som vanlig spørreflate.

## Når arbeidsrommet skal velge RAG-domene automatisk

Velg mønster:
- router-celle
- RAG-kall-celle

Bruk det når:
- arbeidsrommet skal velge mellom flere domener som innovasjon og DiMy
- modellprofil og `source_type` skal settes automatisk

## Anbefalt minimumsoppsett

Hvis du er usikker, start med dette:
1. `RAGCaseCatalogCell`
2. `RAGQueryCell`
3. `RAGCorpusExplorerCell`

Legg bare til `RAGDocumentLinksCell` og `RAGCaseMembersAdminCell` hvis behovet faktisk finnes.

## Kildemessige grenser

Det er ikke dokumentert her:
- en fullstendig standardpakke for alle typer arbeidsrom
- alle mulige cellekombinasjoner i HAVEN
- at andre, ikke navngitte celler bør brukes i stedet

Hvis du trenger et oppsett som går utover dette, må dokumentasjonen utvides først.
