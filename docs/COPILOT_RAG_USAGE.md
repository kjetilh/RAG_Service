# Copilot/agent bruk av rag_service

Dette dokumentet er en praktisk inngang for Copilot Chat, andre kodeagenter og mennesker som skal bruke `rag_service` som prosjekt-RAG.

## Første sjekk

Sjekk at runtime matcher arbeidskopiens API-kontrakt:

```bash
python -m scripts.rag_runtime_check http://127.0.0.1:8000
```

For de to vanlige lokale/VPS-mappede instansene:

```bash
python -m scripts.rag_runtime_check http://127.0.0.1:8101 http://127.0.0.1:8102
```

Hvis denne feiler på manglende ruter som `/v1/cell/cases` eller `/v1/retrieve`, er deployet runtime bak arbeidskopien og må rebuildes/deployes før Copilot kan stole på RAG-en.

## Vanlig agentflyt

1. List cases.
2. Hent status for valgt case.
3. Bruk `retrieve` først når du trenger kontekst til egen resonnering eller en liten lokal modell.
4. Bruk `query` når du vil at `rag_service` skal generere svaret.
5. Siter alltid `citations` fra responsen, ikke bare fritekstsvaret.

## CLI

List cases:

```bash
python -m scripts.rag_cli --base-url http://127.0.0.1:8000 list-cases
```

Status for case:

```bash
python -m scripts.rag_cli --base-url http://127.0.0.1:8000 status dimy_docs
```

Retrieve-only uten generering:

```bash
python -m scripts.rag_cli --base-url http://127.0.0.1:8000 retrieve dimy_docs "Hvordan virker RAGGatewayCell?" --top-k 8 --max-context-chars 12000
```

Generert RAG-svar:

```bash
python -m scripts.rag_cli --base-url http://127.0.0.1:8000 query dimy_docs "Hvordan virker RAGGatewayCell?" --top-k 8
```

Research-token:

```bash
python -m scripts.rag_cli --base-url https://doc.haven.digipomps.org --token "$RAG_RESEARCH_TOKEN" list-cases
python -m scripts.rag_cli --base-url https://doc.haven.digipomps.org --token "$RAG_RESEARCH_TOKEN" retrieve dimy_docs "Hvilke celler finnes for RAG?"
```

Cell gateway:

```bash
python -m scripts.rag_cli \
  --base-url http://127.0.0.1:8000 \
  --cell-secret "$CELL_GATEWAY_SHARED_SECRET" \
  --cell-user-id "$CELL_USER_ID" \
  status dimy_docs
```

## Når du skal velge case

Bruk `dimy_docs` for:

- CellProtocol
- Binding/CellScaffold-integrasjon
- API, endepunkter, kontrakter og runtime-adferd
- implementerte celler og utviklerdokumentasjon

Bruk `dimy_prompts` for:

- hvilke celler som passer sammen
- arbeidsrom og cellesammensetning
- brukerrettede oppskrifter
- prompt- og komponentvalg

Bruk `innovasjon`, `innovasjon_intervjuer` eller `innovasjon_bokskriving` for bokprosjektet.

## Små lokale språkmodeller

For små modeller bør agenten normalt bruke `retrieve`, ikke `query`:

- `retrieve` gjør bare planlegging, søk, pakking og citations.
- `rewrite_query` er av som default for `retrieve`.
- Agenten eller en separat modell kan deretter lese `context_text` og `citations`.

Eksempel med eksplisitt lokal modellprofil for generering:

```bash
python -m scripts.rag_cli \
  --base-url http://127.0.0.1:8000 \
  query dimy_docs "Hva dekker corpus nå?" \
  --model-profile local-small \
  --top-k 6
```

`local-small` må defineres i `LLM_PROFILES_JSON`.

## Feilsøkingsregler for agenter

- Hvis `/health` virker, men `/openapi.json` mangler nye ruter, er runtime sannsynligvis gammel.
- Hvis `status` viser 0 dokumenter, ikke svar som om corpus finnes.
- Hvis `missing_source_types` ikke er tom, si at caset er konfigurert, men ikke indeksert.
- Hvis `database.schema_warnings` inneholder `legacy schema`, kjør migrasjoner/rebuild før du stoler på retrieval.
- Ikke finn på dokumenter, celler eller API-er som ikke finnes i `citations`, `status` eller repoet.
