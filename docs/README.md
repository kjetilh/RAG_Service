# Dokumentasjonsoversikt

Denne mappen inneholder driftsnotater og arbeidsdokumenter.

## Primær dokumentasjon

- Bruk `README.md` i repo-roten som hovedkilde for oppsett, Docker og drift.

## Dokumenter i denne mappen

- `DEPLOY_VPS.md`: konkret VPS-oppsett for testing med flere brukere.
- `DEPLOY_VPS_MULTI_RAG.md`: VPS-oppsett for flere domene-RAG-er + scaffold-tilgang.
- `VPS_DEPLOY_RUNBOOK.md`: kanonisk deploy-sti for `innorag` og `doc` via repo-script, inkludert filmonstre for nar post-sync faktisk skal redeploye `RAG_Service`.
- `VPS_BRUKERE_OG_TILGANG.md`: anbefalt bruker-/gruppeoppsett og tilgangsmodell på VPS.
- `VPS_DOCKER_SETUP.md`: Docker Engine + Compose-oppsett på Hetzner VPS.
- `VPS_NGINX_IP_DEPLOY.md`: Nginx-oppsett med IP-basert HTTPS (self-signed) og deploystatus.
- `VPS_NGINX_DOMENE_DEPLOY.md`: Nginx-oppsett med domenebasert routing og Let's Encrypt.
- `01_Ops_Oppsummering.md`: historisk oppsummering av feil/løsninger under utvikling.
- `02_Kjor_Alt.md`: steg-for-steg lokal kjøring.
- `03_README_Snutt.md`: kort oppstartssnutt.
- `04_Ingest_Move_Files.md`: forklaring av flytting til `done/` og `failed/`.
- `05_Chat_UI.md`: hvordan den enkle chat-UI-en fungerer.
- `RAG_tjeneste_flyt.md`: flytdiagram/skisse av tjenesten.
- `SCAFFOLD_CELL_PROMPTS.md`: promptmaler for router-celle og domene-celler.
- `SYNC_ORCHESTRATOR.md`: orchestrering av kontinuerlig synk mellom flere repoer og dokumentasjons-RAG.
- `NEXTGEN_ROLLBACK_NOTES.md`: rollback-strategi per commit for next-gen RAG-endringer.
- `RAG_SERVICE_API_ENDPUNKTER.md`: eksplisitt inventar over alle registrerte HTTP-endepunkter og auth-grupper.
- `RAG_CASES_SCHEMA.md`: schema og semantikk for `config/rag_cases.yml`.
- `DOC_LIFECYCLE_TOMBSTONES.md`: hvordan `doc_state`, `doc_version`, `delete_missing` og tombstones fungerer.
- `QUERY_PLAN_TRACE_SCHEMA.md`: dokumentert shape for `query_plan`, `trace` og `evaluation_gate`.
- `DEEP_RESEARCH_RAG_VERKTOY_PROMPT.md`: kontekstpakke og ferdig prompt til ChatGPT Deep Research.
- `INTERVIEW_RAG_EVALUATION.md`: evaluering og anbefalt arkitektur for intervju-RAG.
- `INTERVIEW_RAG_RUNBOOK.md`: praktisk runbook for ingest/query mot intervju-case.
- `INNORAG_BOKSKRIVING_RUNBOOK.md`: konkret oppsett for bokskriving med artikler + intervjuer i `innorag`.
- `DEEP_RESEARCH_INTERVIEW_RAG_PROMPT.md`: ferdig Deep Research-prompt for intervju-RAG.
- `CELLPROTOCOL_RAG_STATUS.md`: status og anbefalt retning for a gjore RAG tilgjengelig via `CellConfiguration` og skeleton.
- `CHATGPT_PRO_CELLPROTOCOL_RAG_PROMPT.md`: stram prompt for ekstern ChatGPT Pro-vurdering av RAG -> CellProtocol-integrasjonen.
- `MULTI_RAG_ITERASJON_LOGG.md`: logg over iterasjonsleveranser.
- `Makefile`: hjelpekommandoer for lokal drift.

## Anbefalt praksis videre

- Hold `README.md` oppdatert først.
- Bruk filer i `docs/` til utdypende detaljer eller historikk.
- For API-sporsmal: bruk `docs/RAG_SERVICE_API_ENDPUNKTER.md` som kanonisk inventar.
