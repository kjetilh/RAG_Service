# RAG-tilgjengelighet for CellProtocol, Binding og CellScaffold

Dato: 2026-05-15

## Kort konklusjon

`rag_service` har mye av backend-funksjonaliteten som trengs for CellProtocol-bruk: case-konfigurasjon, hybrid retrieval, kildesitater, cell-gateway-endepunkter, research-API, promptprofiler, modellprofiler og sync/ingest. `CellScaffold` har også allerede en faktisk `RAGGatewayCell`, HTTP-klient, konfigurasjonsfabrikk og katalogoppføring for `cell:///RAGGateway`.

Det som mangler er derfor ikke først og fremst "RAG-motor", men produktiserte forbruksflater og driftspakking:

- deployet runtime må matche koden
- små prosjekt-RAG-er må kunne opprettes uten håndredigering av YAML
- MCP/server- eller tool-overflate for Copilot bør bygges over den nye CLI-en
- deploy/smoke-test må sikre at nye ruter faktisk finnes i kjørende instanser

Min vurdering etter første implementeringsrunde: koden er godt på vei til å være konsumerbar for CellScaffold og Copilot, men kjørende runtime må rebuildes/deployes og et MCP/tool-lag bør komme på plass før en ny agent kan bruke RAG-en helt friksjonsløst.

## Oppdatering etter implementering

Denne rapporten ble fulgt opp med første implementeringsrunde i `rag_service`:

- lagt til retrieval-only API: `POST /v1/retrieve`, `POST /v1/cases/{case_id}/retrieve`, `POST /v1/cell/cases/{case_id}/retrieve` og `POST /v1/research/retrieve`
- lagt til status API: `GET /v1/cases/{case_id}/status`, `GET /v1/cell/cases/{case_id}/status` og `GET /v1/research/cases/{case_id}/status`
- lagt til CellScaffold-forventede admin-ruter for catalog/media publish/status/reindex
- lagt til `scripts/rag_runtime_check.py` for å avdekke gammel runtime før en agent stoler på API-et
- lagt til `scripts/rag_cli.py`, `.github/copilot-instructions.md`, `.github/prompts/use-rag.prompt.md` og `docs/COPILOT_RAG_USAGE.md`
- lagt til valgfri PyCellProtocol-adapter i `app/rag/pycell_gateway.py`, dokumentert i `docs/PYCELL_RAG_GATEWAY.md`
- lagt til kontraktstest som sjekker at runtime-rutene er registrert i FastAPI-appen

Gjenstående viktigste gap er nå case-opprettelse/prosjektmal, MCP/tooling over CLI-en, CellProtocol-identity/RBAC for in-process-adapteren, og faktisk rebuild/deploy/sync av kjørende instanser.

## PyCellProtocol som tillegg

Etter å ha inspisert `/Users/kjetil/Build/Digipomps/HAVEN/PyCellProtocol` vurderer jeg Python CellProtocol som et nyttig tillegg, ikke som erstatning for HTTP/API-sporet.

Funn:

- `PyCellProtocol` har `GeneralCell`, `FunctionCell`, resolver, Swift-kompatible bridge-kommandoer og ASGI scaffold.
- Celler eksponerer async `get`/`set` på keypaths, og scaffolden kan publisere lokale celler via WebSocket bridge.
- `rag_service` kan derfor registrere en `RAGGateway`-celle som kaller RAG-pipeline direkte i samme Python-prosess.

Konsekvens:

- For lokale Python-baserte arbeidsrom og små modeller blir RAG lettere å konsumere enn via HTTP.
- For CellScaffold/Binding endrer det ikke behovet for HTTP eller bridge-kompatibel remote-tilgang, men gir en ekstra runtime-variant.
- Den viktigste sikkerhetsforskjellen er at in-process-adapteren er en trusted adapter; flerbruker/RBAC må avklares før admin-keypaths eksponeres bredt.

Ny anbefaling: behold HTTP som canonical ekstern kontrakt, men bruk PyCellProtocol-adapteren som lokal/in-process `cell:///RAGGateway` for Python-baserte celler, test og småmodell-flyt.

## Hva som finnes i de ulike RAG-ene nå

Kilde: `config/rag_cases.yml`.

| Case | Formål | Source types | Promptprofil | Kommentar |
| --- | --- | --- | --- | --- |
| `dimy_docs` | Utvikler- og kodeassistent-RAG for CellProtocol, kuraterte interne CellScaffold-dokumenter, implementerte celler og dokumentert kodebruk | `haven_docs`, `cellprotocol_docs`, `cellscaffold_internal_docs`, `dimy_private_dev_docs` | `system_persona_dimy_developer.md`, `answer_template_dimy_developer.md` | Riktig case for Binding/CellScaffold/API/kontrakter. Private source types krever intern instans eller tilgangskontroll. |
| `dimy_prompts` | Brukerrettet verktøy for å sette sammen celler, komponenter og arbeidsrom | `prompt_docs` | `system_persona_dimy_components.md`, `answer_template_dimy_components.md` | Riktig case for "hvilke celler passer sammen?" og workspace-oppskrifter. |
| `innovasjon` | Innovasjonsledelse og innovasjonsfag | `innovasjonsledelse`, `innovasjonsfag` | global/default | Generell fag-RAG. |
| `innovasjon_intervjuer` | Lederintervjuer for bokprosjektet, særlig kollektiv mening per fast spørsmål | `innovasjon_intervju_transcript` | `system_persona_interview.md`, `answer_template_interview.md` | Har egne kollektiv-oppsummeringsendepunkter. |
| `innovasjon_bokskriving` | Skrivehjelp for innovasjonsledelse-boka med artikler og intervjuer | `innovasjonsledelse`, `innovasjonsfag`, `innovasjon_intervju_transcript` | `system_persona_bokskriving.md`, `answer_template_bokskriving.md` | Hybrid case for manus/kapittel/arbeidshypoteser. |

Merk: `docs/RAG_CASES_SCHEMA.md` er utdatert. Den sier at `dimy_prompts` og `innovasjon_bokskriving` ikke finnes, mens de faktisk finnes i `config/rag_cases.yml`.

Operativt lokalt per 2026-05-15:

- Docker-instansene på `127.0.0.1:8101` og `127.0.0.1:8102` svarer på `/health`.
- `python -m scripts.rag_runtime_check http://127.0.0.1:8101 http://127.0.0.1:8102 --timeout 2` feiler fordi OpenAPI mangler den nye public/cell/research/admin-kontrakten.
- Begge lokale Docker-databasene hadde 0 dokumenter og manglet nyere `doc_state`-kolonne.
- `documents.csv` i repoet har 125 eldre dokumentrader, fordelt på `paper` 111 og `unknown` 14, men disse source typene matcher ikke de nåværende case-definisjonene direkte.

Det betyr at arbeidskopien har en nyere og rikere API-overflate enn den kjørende lokale runtime-en.

Verifikasjon kjørt:

- Import av `app.main` i `.venv` viser at arbeidskopien registrerer `/v1/cases`, `/v1/cell/cases`, `/v1/research/cases`, `/v1/admin/case-prompt-profiles` og øvrige nye ruter.
- Full testpakke etter implementering: 165 beståtte tester.

## Tilgjengelighet for CellScaffold

CellScaffold er best posisjonert akkurat nå.

Funn:

- `Sources/App/Services/RAGGatewayHTTPClient.swift` kan kalle `listCases`, `query`, `corpus`, `links`, `collectiveSummary`, `members` og prompt-admin mot `rag_service`.
- `Sources/App/Cells/RAG/RAGGatewayCell.swift` eksponerer keypaths som `cases.list`, `query.run`, `corpus.list`, `links.case`, `links.document`, `interviews.collectiveSummary`, `members.*`, `catalog.*` og `media.*`.
- `Sources/App/Cells/RAG/RAGGatewayConfigurationFactory.swift` lager en `CellConfiguration` for `cell:///RAGGateway`.
- `ConfigurationCatalogCell` publiserer `RAG Gateway Workspace` og `RAG Prompt Admin`.
- Det finnes tester for gatewaycell, HTTP-klient og katalogoppføring.

Viktig gap:

- `rag_service` har nå `/v1/admin/catalog/*` og `/v1/admin/media/*`, men de må kontrakttestes mot `RAGGatewayHTTPClient` og deployes før CellScaffold kan stole på dem.
- De kjørende RAG-containerne ser ut til å være gamle eller tomme, så CellScaffold-integrasjonen er ikke pålitelig uten deploy/migrering/sync.

Vurdering: god kodeintegrasjon, svak runtime-kontrakt.

## Tilgjengelighet for Binding

Binding har ikke en egen RAG-klientflate i repoet jeg fant. Den er primært en app-side `CellConfiguration`/Skeleton/remote-CellScaffold-klient.

Funn:

- Binding kan laste og rendre `CellConfiguration`.
- Binding har remote `CellScaffold`-kobling og bridge-/catalog-støtte.
- Det finnes bare indirekte RAG-spor: prompt-evalueringsfixture med `rag.query.nb`, og generell remote/catalog-infrastruktur.

Konsekvens:

- Binding kan sannsynligvis konsumere RAG via `CellScaffold` dersom `RAGGateway` publiseres som remote cell/configuration og bridge/admission fungerer.
- Binding er ikke klar som en standalone direkte RAG-klient uten enten en remote `CellScaffold`-celle eller en egen `RAGGateway`/HTTP-adapter i Binding.

Vurdering: indirekte tilgjengelig via CellScaffold, ikke direkte.

## Tilgjengelighet for Copilot Chat

Per offisiell dokumentasjon støtter Copilot/VS Code:

- repo-instruksjoner i `.github/copilot-instructions.md`
- path-spesifikke `.github/instructions/**/*.instructions.md`
- `AGENTS.md` i flere Copilot-miljøer
- prompt files i `.github/prompts`
- MCP-servere som verktøy i agentmodus

`rag_service` har et godt dokument for arkitektur-review (`docs/CHATGPT_PRO_CELLPROTOCOL_RAG_PROMPT.md`), men ikke en praktisk "bruk RAG-en fra Copilot" pakke.

Det som er lagt til for at Copilot Chat enklere skal konsumere RAG-en:

1. `.github/copilot-instructions.md` i `rag_service`, som peker til praktisk RAG-bruksdokumentasjon.
2. `.github/prompts/use-rag.prompt.md` med konkrete kommandoer og forventet output.
3. `scripts/rag_cli.py`, slik at Copilot kan kjøre `list-cases`, `status`, `retrieve` og `query` uten å finne på curl-kall og headers selv.
4. Status-endepunkter som sier hvilke cases, source types, modellprofiler og corpustall som faktisk er aktive.

Det som fortsatt mangler er tilsvarende instruksjonsfiler i `CellScaffold` og `Binding`, pluss en MCP-server over de samme funksjonene hvis vi vil gi Copilot en ren tool-overflate.

Vurdering: i dag må en god agent lese mye repo-kontekst og gjette litt. Med en liten MCP/CLI + promptfil kan dette bli lett.

## Små prosjekt-RAG-er og lokale modeller

Dette ser teknisk lovende ut, men trenger produktpakking.

Det som allerede hjelper:

- `LLM_PROVIDER=openai_compat` og `LLM_BASE_URL` gjør at tjenesten kan peke mot OpenAI-kompatible lokale servere.
- `model_profile` kan velges per request gjennom `LLM_PROFILES_JSON`.
- Default embedding er `sentence-transformers/all-MiniLM-L6-v2`, som er en liten lokal embeddingmodell.
- Retrieval er hybrid: vector + lexical.
- `top_k`, source filters, case filters og promptprofiler finnes.

Eksterne kilder bekrefter at både Ollama og llama.cpp kan eksponere OpenAI-kompatible chat-completions-endepunkter, så dagens `openai_compat`-provider passer godt som integrasjonspunkt for lokale småmodeller.

Svakhetene for små modeller etter første implementeringsrunde:

- Retrieval-only/context endpoint finnes nå, men bør få mer modellprofil-metadata og bedre anbefalte defaultverdier per modell.
- Embedding-dimensjonen er hardkodet til `vector(384)`, så bytte av embeddingmodell krever bevisst migrering/rebuild.
- Det mangler en modellprofil-metadata-kontrakt: context window, supports JSON, supports tools, recommended `top_k`, rewrite on/off, rerank on/off.
- Query rewrite bruker LLM og kan være for dyrt/svakt for små modeller; dette bør kunne styres per modellprofil.
- Fler-modellflyt finnes ikke som eksplisitt API: f.eks. liten lokal modell for klassifisering/ruting, sterkere modell for syntese ved behov.

## Anbefalt utvikling i `rag_service`

Prioritet 1: runtime-kontrakt og deploy

- Sørg for at Docker/VPS image faktisk eksponerer samme ruter som `app.main`.
- Kjør migrasjoner slik at `doc_state`, `rag_case_access` og prompt runtime config finnes i deployet database.
- Bruk `python -m scripts.rag_runtime_check <base-url>` som smoke-test; den feiler hvis sentrale public/cell/research/admin-ruter mangler.
- Bruk `GET /v1/cases/{case_id}/status` eller CLI `status` som corpus/status-sjekk per instance.

Prioritet 2: Copilot-konsumering

- `docs/COPILOT_RAG_USAGE.md`, `.github/copilot-instructions.md`, `.github/prompts/use-rag.prompt.md` og `scripts/rag_cli.py` finnes nå.
- Deretter bygg MCP-server over samme funksjoner.
- Kopier eller tilpass Copilot-instruksjoner inn i `CellScaffold` og `Binding`.

Prioritet 3: små prosjekt-RAG-er

- Legg til `POST /v1/admin/cases` eller en trygg CLI for å opprette case fra prosjektmappe.
- Status- og retrieve-endepunkter finnes nå; neste steg er prosjektmal og case-opprettelse.
- Legg til prosjektmal: `rag_project.yml` eller `.rag/case.yml`.

Prioritet 4: CellScaffold-kontraktsrydding

- `/v1/admin/catalog/publish`, `/v1/admin/catalog/reindex`, `/v1/admin/catalog/status`, `/v1/admin/media/publish` og `/v1/admin/media/status` er implementert i `rag_service`.
- Lag kontraktstest mellom `RAGGatewayCell.contracts` og faktisk `rag_service` OpenAPI.
- Publiser en minimal "query only" RAGGateway-konfig først, og hold catalog/media som senere admin-utvidelser.

## Kilder sjekket på nett

- GitHub Docs: repository custom instructions, `.github/copilot-instructions.md`, `.github/instructions`, `AGENTS.md`: https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions
- GitHub Docs: supportmatrise for Copilot custom instructions: https://docs.github.com/en/copilot/reference/custom-instructions-support
- VS Code Docs: custom instructions: https://code.visualstudio.com/docs/copilot/customization/custom-instructions
- VS Code Docs: prompt files: https://code.visualstudio.com/docs/copilot/customization/prompt-files
- VS Code Docs: MCP-servere i Copilot Chat/agentmodus: https://code.visualstudio.com/docs/copilot/customization/mcp-servers
- Ollama docs: OpenAI-compatible `/v1/chat/completions`: https://docs.ollama.com/api/openai-compatibility
- llama.cpp docs: `llama-server` med OpenAI-kompatible chat completions og embeddings: https://www.mintlify.com/ggml-org/llama.cpp/inference/server
