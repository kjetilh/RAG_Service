# Når du skal låse et arbeidsrom til ett case, og når du skal bruke router

Dette dokumentet er laget for spørsmål om valg mellom et fast case-oppsett og et router-oppsett.

Grunnlaget er den dokumenterte scaffold-promptlogikken og de beskrevne RAG-cellene i denne repoen.

## Velg fast case når arbeidsrommet har ett tydelig formål

Et fast case-oppsett passer når arbeidsrommet er laget for ett bestemt kunnskapsdomene.

Dokumenterte eksempler:
- en hardkodet innovasjon-celle
- en hardkodet DiMy-celle

Dette er et godt valg når:
- brukeren ikke skal ta stilling til domene
- alle spørsmålene skal gå til samme case
- du vil holde oppsettet enkelt

Typisk kombinasjon:
- `RAGCaseCatalogCell`
- `RAGQueryCell`

## Velg router når arbeidsrommet må veksle mellom domener

Et router-oppsett passer når samme arbeidsrom skal kunne sende spørsmål til ulike RAG-tjenester.

Dokumentert mønster:
- router-cellen returnerer `domain`, `model_profile` og `source_types`
- RAG-kall-cellen sender forespørselen videre til riktig endpoint

Dette er et godt valg når:
- brukeren kan spørre på tvers av innovasjon og DiMy
- arbeidsrommet må velge modellprofil per spørsmål
- `source_type` skal settes automatisk

## Ikke bruk router bare fordi det finnes flere case

Et fast case er bedre når:
- arbeidsrommet skal være stabilt og forutsigbart
- brukeren jobber mot ett kjent corpus
- målet ikke er automatisk domenevalg

En router er bedre når:
- brukerens spørsmål kan skifte mellom domener
- samme arbeidsrom skal støtte både raske og mer komplekse kall

## Hvordan velge modellprofil

Det dokumenterte mønsteret sier:
- bruk `openai-mini` for raske standardspørsmål
- bruk `openai-4o` for mer komplekse analyser

Du skal ikke anta andre profiler hvis de ikke er dokumentert i oppsettet.

## Hvordan velge source_type

Det dokumenterte router-mønsteret sier at router-cellen skal sette relevante `source_type`-filtre.

Praktisk konsekvens:
- bruk et fast case når `source_type` er kjent på forhånd
- bruk router når `source_type` må avgjøres av spørsmålet

## En enkel beslutningsregel

Bruk fast case hvis arbeidsrommet kan beskrives slik:
- "Dette arbeidsrommet spør bare ett case."

Bruk router hvis arbeidsrommet må beskrives slik:
- "Dette arbeidsrommet må først finne ut hvilket case og hvilken modellprofil som passer."

## Dokumentasjonsgrense

Denne repoen dokumenterer mønsteret for router og hardkodede domener, men ikke alle tenkelige varianter av et flertrinns arbeidsrom.
