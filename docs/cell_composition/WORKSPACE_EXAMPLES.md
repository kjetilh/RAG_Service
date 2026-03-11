# Konkrete arbeidsromseksempler for dokumenterte RAG-celler

Dette dokumentet gir noen fa, konkrete arbeidsromseksempler som holder seg til dokumenterte RAG-celler og dokumenterte oppskrifter.

Hvis et oppsett krever andre celler eller skjermflyt enn det som er navngitt her, er det ikke dekket av denne dokumentasjonen ennå.

## 1. Dokumentasjonsarbeidsrom for utviklere

Bruk dette når brukeren skal lese dokumentasjon, spore kilder og stille tekniske spørsmål.

Dokumenterte byggesteiner:
- `RAGCaseCatalogCell`
- `RAGQueryCell`
- `RAGCorpusExplorerCell`
- `RAGDocumentLinksCell`

Praktisk oppsett:
1. Lås arbeidsrommet til `dimy_docs`, eller la `RAGCaseCatalogCell` velge det.
2. Bruk `RAGQueryCell` som hovedflate for tekniske spørsmål.
3. Bruk `RAGCorpusExplorerCell` for å kontrollere hvilke dokumenter som finnes.
4. Bruk `RAGDocumentLinksCell` når brukeren må følge lenker videre.

Hvorfor dette passer:
- det støtter API-er, kontrakter, implementasjon og runtime-adferd
- det gjør det enkelt å kontrollere kilder før kode endres

## 2. Arbeidsrom for brukerrettet cellesammensetning

Bruk dette når brukeren vil finne ut hvordan celler kan settes sammen til et arbeidsrom.

Dokumenterte byggesteiner:
- `RAGQueryCell`
- `RAGCorpusExplorerCell`
- `RAGDocumentLinksCell`

Praktisk oppsett:
1. Lås arbeidsrommet til `dimy_prompts`.
2. Bruk `RAGQueryCell` til spørsmål om byggesteiner, oppskrifter og arbeidsrom.
3. Bruk `RAGCorpusExplorerCell` for å finne relevante guider og oppskrifter.
4. Bruk `RAGDocumentLinksCell` for å følge forbindelser mellom guider og mønstre.

Hvorfor dette passer:
- dette caset er kuratert for brukerrettet komposisjon, ikke dyp implementasjon
- det reduserer risikoen for at brukeren havner i teknisk dokumentasjon når spørsmålet egentlig handler om oppsett

## 3. Låst produktarbeidsrom med fast case

Bruk dette når arbeidsrommet er laget for ett tydelig formål og brukeren ikke skal velge case selv.

Dokumenterte byggesteiner:
- `RAGQueryCell`
- valgfritt `RAGCorpusExplorerCell`

Praktisk oppsett:
1. Hardkod caset i arbeidsrommet.
2. Bruk `RAGQueryCell` som primærflate.
3. Legg til `RAGCorpusExplorerCell` bare hvis brukeren må se dekning i corpus.

Anbefalt valg:
- bruk `dimy_docs` for tekniske arbeidsrom
- bruk `dimy_prompts` for komposisjonsarbeidsrom

Hvorfor dette passer:
- arbeidsrommet blir enklere for sluttbrukeren
- det blir færre feilvalg av case

## 4. Router-basert arbeidsrom på tvers av domener

Bruk dette når samme arbeidsrom skal kunne velge mellom ulike kunnskapsdomener.

Dokumenterte byggesteiner:
- router-celle
- RAG-kall-celle

Praktisk oppsett:
1. router-cellen velger domene, modellprofil og relevante filtre
2. RAG-kall-cellen sender foresporselen videre til riktig tjeneste
3. bruk fast case i stedet hvis arbeidsrommet bare har ett tydelig domene

Hvorfor dette passer:
- brukeren slipper å kjenne alle backend-tjenestene
- arbeidsrommet kan håndtere flere typer spørsmål uten at alt blandes i samme case
