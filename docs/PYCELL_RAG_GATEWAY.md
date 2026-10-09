# PyCellProtocol RAG Gateway

`PyCellProtocol` gir en nyttig tilleggsflate for `rag_service`: RAG kan eksponeres som en CellProtocol-celle i samme Python-prosess, uten at cellen må gå via `rag_service` sitt HTTP-API.

Dette erstatter ikke HTTP-flaten. Det er en in-process adapter for lokale/verktøydrevne runtime-miljøer der Python-prosessen allerede har tilgang til database, settings, embeddings og RAG-pipeline.

## Hva dette endrer

Det endrer ikke hovedkonklusjonen om at `rag_service` fortsatt trenger stabile HTTP-kontrakter for CellScaffold, Binding, research-klienter og deployede tjenester.

Det gir derimot et sterkt tillegg:

- lavere friksjon for lokale Python-baserte celler
- ingen risiko for at adapteren kaller en gammel HTTP-container
- direkte gjenbruk av `routes_chat._run_query`, `routes_chat._run_retrieve`, `_case_status` og admin-publish-funksjoner
- en naturlig bro videre til CellProtocol keypaths og Swift-kompatibel WebSocket bridge via `PyCellProtocol`

## Valgfri adapter i rag_service

Adapteren ligger i:

- `app/rag/pycell_gateway.py`

Den er valgfri. `rag_service` får ikke en hard dependency på `PyCellProtocol`; hvis `cellprotocol` ikke er importbar, feiler `create_rag_gateway_cell()` med en tydelig `PyCellProtocolUnavailable`.

## Eksponerte keypaths

- `cases.list` (`get`)
- `runtime.contract` (`get`)
- `status.get` (`set`, payload med `case_id`)
- `query.run` (`set`, `QueryRequest`)
- `retrieve.run` (`set`, `RetrieveRequest`)
- `catalog.publish` (`set`)
- `catalog.reindex` (`set`)
- `catalog.status` (`set`)
- `media.publish` (`set`)
- `media.status` (`set`)

`retrieve.run` er viktigst for små lokale modeller og fler-modelloppsett: den returnerer pakket `context_text`, `citations`, `retrieval_debug` og `trace` uten slutt-generering.

## Kjøre som PyCellProtocol scaffold

Fra `rag_service`:

```bash
PYTHONPATH=.:/Users/kjetil/Build/Digipomps/HAVEN/PyCellProtocol/src \
  uvicorn app.rag.pycell_gateway:create_app --factory --host 127.0.0.1 --port 8081
```

Da registreres `cell:///RAGGateway` i PyCellProtocol scaffolden, med bridge-endepunktet som PyCellProtocol allerede tilbyr.

Rask import-test:

```bash
PYTHONPATH=.:/Users/kjetil/Build/Digipomps/HAVEN/PyCellProtocol/src \
  python -c "from app.rag.pycell_gateway import create_app, create_rag_gateway_cell; print(create_app().title, create_rag_gateway_cell().name)"
```

## Viktige avgrensinger

- Dette er en trusted in-process adapter. Den bør ikke automatisk brukes som internettvendt adminflate.
- HTTP-endepunktene må fortsatt finnes for deploy, remote CellScaffold, Binding og research-bruk.
- Database, migrations, corpus-sync og modellprofiler er fortsatt samme underliggende krav.
- Cell-level identity/RBAC bør avklares før adapteren brukes for flerbrukerproduksjon. Dagens adapter bruker vanlig case-visibility for query/retrieve/status, men admin-publish-keypaths forutsetter en betrodd runtime.

## Anbefalt rolle i arkitekturen

Bruk PyCellProtocol-adapteren som et tillegg:

- lokal RAG-celle for Python-baserte arbeidsrom
- test-/dev-verktøy som slipper å gå via HTTP
- bro for små lokale modeller som vil konsumere `retrieve.run`
- tidlig CellProtocol-kontraktstest før tilsvarende Swift/CellScaffold-flate hardnes

Behold HTTP-flaten som canonical ekstern kontrakt:

- CellScaffold remote gateway
- Binding via CellScaffold/bridge
- deployet research API
- Copilot/CLI/MCP på tvers av prosesser
