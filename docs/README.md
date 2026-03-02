# Dokumentasjonsoversikt

Denne mappen inneholder driftsnotater og arbeidsdokumenter.

## Primær dokumentasjon

- Bruk `README.md` i repo-roten som hovedkilde for oppsett, Docker og drift.

## Dokumenter i denne mappen

- `DEPLOY_VPS.md`: konkret VPS-oppsett for testing med flere brukere.
- `DEPLOY_VPS_MULTI_RAG.md`: VPS-oppsett for flere domene-RAG-er + scaffold-tilgang.
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
- `DEEP_RESEARCH_RAG_VERKTOY_PROMPT.md`: kontekstpakke og ferdig prompt til ChatGPT Deep Research.
- `MULTI_RAG_ITERASJON_LOGG.md`: logg over iterasjonsleveranser.
- `Makefile`: hjelpekommandoer for lokal drift.

## Anbefalt praksis videre

- Hold `README.md` oppdatert først.
- Bruk filer i `docs/` til utdypende detaljer eller historikk.
