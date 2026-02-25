# Deploy multi-RAG på samme VPS (scaffold + flere domener)

Denne guiden kjører to isolerte RAG-tjenester på samme VPS:

- `rag_innovasjon_api` + `rag_innovasjon_db`
- `rag_dimy_api` + `rag_dimy_db`

Begge kan nås fra et scaffold via delt Docker-nettverk (`scaffold_shared`).
Domeneoppsett brukt i staging:

- `https://innorag.haven.digipomps.org` -> `rag_innovasjon_api` (`127.0.0.1:8101`)
- `https://doc.haven.digipomps.org` -> `rag_dimy_api` (`127.0.0.1:8102`)

## 1) Forutsetninger

- Docker Engine + Compose plugin på VPS
- Repo klonet på VPS
- Scaffold kjører i container på samme VPS (eller kan kobles til samme Docker-nettverk)

## 2) Forbered miljøfil

Kopier miljømal:

```bash
cp docker/.env.vps.multi.example docker/.env.vps.multi
```

Rediger `docker/.env.vps.multi`:

- sett unike DB-passord per domene
- sett unike admin-nøkler per domene
- sett LLM nøkler/modeller per domene
- verifiser upload-stier

Generer nøkler:

```bash
openssl rand -hex 32
```

## 3) Opprett delt nettverk mot scaffold

```bash
docker network create scaffold_shared
```

Hvis nettverket finnes fra før, er det ok.

## 4) Start begge RAG-stacker

```bash
docker compose \
  --env-file docker/.env.vps.multi \
  -f docker/docker-compose.vps.yml \
  up -d --build
```

Ved endring i Python-avhengigheter (f.eks. ingest for PDF/DOCX):

```bash
docker compose \
  --env-file docker/.env.vps.multi \
  -f docker/docker-compose.vps.yml \
  build --no-cache rag_innovasjon_api rag_dimy_api

docker compose \
  --env-file docker/.env.vps.multi \
  -f docker/docker-compose.vps.yml \
  up -d
```

API-image skal installere extras:

```bash
pip install -e '.[pdf,docx,html]'
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.10.0
pip install sentence-transformers>=3.0.0
```

Dette dekker også AES-krypterte PDF-filer via `cryptography` i `pdf`-gruppen,
og holder image mindre ved CPU-variant av torch.

Verifiser i begge API-containere:

```bash
docker exec docker-rag_innovasjon_api-1 python -c "import pypdf, docx, bs4, lxml, cryptography; print('innovasjon ok')"
docker exec docker-rag_dimy_api-1 python -c "import pypdf, docx, bs4, lxml, cryptography; print('dimy ok')"
```

Sjekk tjenester:

```bash
docker compose --env-file docker/.env.vps.multi -f docker/docker-compose.vps.yml ps
curl http://127.0.0.1:8101/health
curl http://127.0.0.1:8102/health
```

Verifiser offentlig domene-ruting:

```bash
curl https://innorag.haven.digipomps.org/health
curl https://doc.haven.digipomps.org/health
```

## 5) Koble scaffold-container til nettverket

Hvis scaffold ikke allerede er på `scaffold_shared`:

```bash
docker network connect scaffold_shared <scaffold_container_name>
```

Interne URL-er fra scaffold:

- `http://rag_innovasjon_api:8000/v1/chat`
- `http://rag_dimy_api:8000/v1/chat`

## 6) Ingest per domene

Legg filer i:

- `uploads/innovasjon/...`
- `uploads/dimy/...`

Eksempel ingest innovasjon:

```bash
curl -X POST http://127.0.0.1:8101/v1/admin/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $RAG_INNOVASJON_ADMIN_API_KEY" \
  -d '{"path":"innovasjonsledelse","source_type":"innovasjonsledelse"}'
```

Eksempel ingest DiMy:

```bash
curl -X POST http://127.0.0.1:8102/v1/admin/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $RAG_DIMY_ADMIN_API_KEY" \
  -d '{"path":"cell_haven_docs","source_type":"haven_docs"}'
```

Anbefalt `source_type`-standard:

- Innovasjon: `innovasjonsledelse`, `immovasjonsfag`
- Dokumentasjon (`doc`): `haven_docs`, `cellprotocol_docs`

### 6.1 Last opp CellProtocol/HAVEN-dokumenter fra lokal checkout

Eksempel (kjores lokalt, laster opp til VPS):

```bash
set -euo pipefail
SRC=/tmp/rag_doc_bundle
rm -rf "$SRC"
mkdir -p "$SRC"

for repo in \
  /Users/kjetil/Build/Digipomps/HAVEN/CellProtocol \
  /Users/kjetil/Build/Digipomps/HAVEN/CellProtocolDocuments \
  /Users/kjetil/Build/Digipomps/HAVEN/CellScaffold
do
  name="$(basename "$repo")"
  mkdir -p "$SRC/$name"
  git -C "$repo" ls-files -z | while IFS= read -r -d '' f; do
    case "$f" in
      *.md|*.markdown|*.txt|*.html|*.htm|*.pdf|*.docx)
        mkdir -p "$SRC/$name/$(dirname "$f")"
        cp "$repo/$f" "$SRC/$name/$f"
        ;;
    esac
  done
done

COPYFILE_DISABLE=1 tar -C "$SRC" -czf - . | \
ssh -i ~/.ssh/id_ed25519_hetzner root@89.167.90.101 '
  set -e
  rm -rf /srv/ops/rag_service/uploads/dimy/cell_haven_docs
  mkdir -p /srv/ops/rag_service/uploads/dimy/cell_haven_docs
  tar -C /srv/ops/rag_service/uploads/dimy/cell_haven_docs -xzf -
'
```

## 7) Modellbytte per request (`model_profile`)

API-et støtter nå `model_profile` i `/v1/chat` og `/v1/chat/stream`.

Eksempel request:

```bash
curl -X POST http://127.0.0.1:8101/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Oppsummer mission-oriented innovation policy",
    "model_profile": "openai-4o",
    "filters": { "source_type": ["innovasjonsledelse"] }
  }'
```

Konfigurer profiler i `RAG_INNOVASJON_LLM_PROFILES_JSON` eller `RAG_DIMY_LLM_PROFILES_JSON`:

```env
RAG_INNOVASJON_LLM_PROFILES_JSON={"openai-mini":{"provider":"openai_compat","base_url":"https://api.openai.com/v1","api_key_env":"RAG_INNOVASJON_LLM_API_KEY","model":"gpt-4o-mini"},"openai-4o":{"provider":"openai_compat","base_url":"https://api.openai.com/v1","api_key_env":"RAG_INNOVASJON_LLM_API_KEY","model":"gpt-4o"}}
```

Hvis `model_profile` mangler, brukes default `LLM_*`-verdier for den tjenesten.

## 8) Eksponering via reverse proxy

Hold API-portene bundet til `127.0.0.1` (som i compose-filen). Eksponer offentlig via Nginx/Caddy med HTTPS.

Anbefalt ruting:

- `innorag.haven.digipomps.org` -> `127.0.0.1:8101`
- `doc.haven.digipomps.org` -> `127.0.0.1:8102`

## 9) Drift

Restart:

```bash
docker compose --env-file docker/.env.vps.multi -f docker/docker-compose.vps.yml restart
```

Stopp:

```bash
docker compose --env-file docker/.env.vps.multi -f docker/docker-compose.vps.yml down
```

Logs:

```bash
docker compose --env-file docker/.env.vps.multi -f docker/docker-compose.vps.yml logs -f rag_innovasjon_api rag_dimy_api
```
