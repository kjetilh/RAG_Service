# Multi-RAG iterasjonslogg

Denne loggen dokumenterer endringer i tre leveranseiterasjoner.

## Iterasjon 1: Infrastruktur på VPS

Mål:

- kjøre flere RAG-instansser på samme VPS
- isolere data og ingest per domene
- gi scaffold intern tilgang via Docker-nettverk

Levert:

- `docker/docker-compose.vps.yml`
- `docker/.env.vps.multi.example`

Resultat:

- to separate API+DB stacks (`innovasjon`, `dimy`)
- egne volumer og uploads-kataloger per domene
- delt nettverk `scaffold_shared` for intern trafikk fra scaffold

## Iterasjon 2: Byttbar språkmodell per request

Mål:

- velge modell dynamisk fra scaffold-celle uten restart av service

Levert:

- `model_profile` i request-kontrakt
- `LLM_PROFILES_JSON` støtte for profilkart
- 400-feil for ukjent/ugyldig profil

Endrede filer:

- `app/models/schemas.py`
- `app/api/routes_chat.py`
- `app/rag/pipeline.py`
- `app/rag/generate/composer.py`
- `app/rag/generate/llm_provider.py`
- `app/settings.py`
- `.env.example`
- `tests/test_model_profiles.py`

## Iterasjon 3: Operativ dokumentasjon + scaffold-prompter

Mål:

- gjøre deploy og cell-oppsett direkte kjørbart av teamet

Levert:

- `docs/DEPLOY_VPS_MULTI_RAG.md`
- `docs/SCAFFOLD_CELL_PROMPTS.md`

Resultat:

- konkret kjøreplan for VPS
- konkrete promptmaler for router-celle og domeneceller
- standard for `source_type` i begge domener
