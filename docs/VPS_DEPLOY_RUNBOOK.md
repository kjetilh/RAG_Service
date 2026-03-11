# VPS deploy-runbook

Denne fila beskriver den operative deploy-stien for `innorag` og `doc` pa VPS.

## Kanonisk deploy-metode

Bruk script i repoet, ikke ad hoc `docker compose --build`-kommandoer:

- `scripts/deploy_innorag.sh`
- `scripts/deploy_doc.sh`

Scriptet gjor dette i fast rekkefolge:

1. bygger image med `docker build`
2. stopper og fjerner eksisterende API-container for tjenesten
3. starter tjenesten igjen med `docker compose up -d --no-deps`
4. venter pa health-check

Dette er valgt fordi `docker compose build`/recreate har vaert ustabilt pa VPS-en.

## Normal bruk pa VPS

Kjor fra driftstreet:

```bash
cd /srv/ops/rag_service
./scripts/deploy_innorag.sh
./scripts/deploy_doc.sh
```

## Bygg fra ren repo-speilklone

Hvis `/srv/ops/rag_service` er dirty, men den rene speilklonen i `/srv/ops/repos/RAG_Service` er oppdatert, kan scriptet bygge fra speilklonen og fortsatt bruke driftens env/compose-filer:

```bash
cd /srv/ops/rag_service
SOURCE_ROOT=/srv/ops/repos/RAG_Service OPS_ROOT=/srv/ops/rag_service ./scripts/deploy_innorag.sh
SOURCE_ROOT=/srv/ops/repos/RAG_Service OPS_ROOT=/srv/ops/rag_service ./scripts/deploy_doc.sh
```

Betydning:

- `SOURCE_ROOT`: kildekoden som bakes inn i image
- `OPS_ROOT`: driftens `docker/.env.vps.multi` og `docker/docker-compose.vps.yml`

Dette er den tryggeste ma ten a redeploye etter repo-sync nar deploy-checkouten ikke er ren.

## Post-sync-flyt

`/srv/ops/rag_service/scripts/run_doc_sync.sh` skal ikke bruke manuelle `docker compose --build`-kommandoer.

Hvis repo-speilet for `RAG_Service` flytter seg under sync, skal post-sync-flyten redeploye med:

```bash
SOURCE_ROOT=/srv/ops/repos/RAG_Service OPS_ROOT=/srv/ops/rag_service ./scripts/deploy_innorag.sh
SOURCE_ROOT=/srv/ops/repos/RAG_Service OPS_ROOT=/srv/ops/rag_service ./scripts/deploy_doc.sh
```

Deretter skal verifiseringene kjores.

## Health og rask kontroll

```bash
curl -fsS http://127.0.0.1:8101/health
curl -fsS http://127.0.0.1:8102/health
```

Eksempel pa funksjonell kontroll av `doc`:

```bash
curl -fsS https://doc.haven.digipomps.org/health
```

## Nar scriptet skal brukes

Bruk deploy-script ved:

- kodeendringer i `app/`, `scripts/`, `prompts/` eller `config/`
- endringer i promptprofiler som skal bli runtime-default
- endringer i compose/env som krever ny containerstart

Ikke bruk deploy-script bare fordi dokumentkorpuset er synket. Da holder det med sync + verifisering.
