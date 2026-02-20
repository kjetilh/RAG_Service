# Deploy på VPS (for testing av flere brukere)

Denne guiden setter opp tjenesten slik at andre kan teste chat-endepunktene, mens admin-endepunkter er beskyttet med API-nøkkel.

## 1. Forutsetninger på VPS

- Docker Engine + Compose plugin
- En Linux-bruker med SSH-tilgang
- DNS-navn eller offentlig IP

## 2. Klon repo og gå til prosjektet

```bash
git clone git@github.com:kjetilh/RAG_Service.git
cd RAG_Service
```

## 3. Sett miljøvariabler

```bash
cp .env.example .env
```

Sett minst disse i `.env`:

```env
APP_ENV=prod
LLM_API_KEY=YOUR_REAL_KEY
ADMIN_API_KEY=CHANGE_TO_A_LONG_RANDOM_VALUE
INGEST_ROOT=/data/uploads
```

Generer en sterk admin-nøkkel:

```bash
openssl rand -hex 32
```

## 4. Start stacken

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Sjekk status:

```bash
docker compose -f docker/docker-compose.yml ps
curl http://localhost:8000/health
```

## 5. Last opp dokumenter for ingest

Compose mapper lokal mappe `uploads/` til `/data/uploads` i API-containeren.

Opprett mapper:

```bash
mkdir -p uploads/team_docs
```

Last opp fra din maskin til VPS:

```bash
scp -r ./mine_filer/* user@your-vps:/path/to/RAG_Service/uploads/team_docs/
```

## 6. Kjør ingest via admin-endepunkt

Alle `POST /v1/admin/*` krever header `X-API-Key`.

Eksempel ingest:

```bash
curl -X POST http://localhost:8000/v1/admin/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -d '{"path":"team_docs","source_type":"paper"}'
```

Viktig:
- `path` må være under `INGEST_ROOT`.
- `path` kan være relativ (f.eks. `team_docs`) eller absolutt under `/data/uploads`.
- Filer flyttes automatisk til `uploads/done/...` ved suksess.
- Filer flyttes automatisk til `uploads/failed/...` ved feil.
- `done/` og `failed/` opprettes automatisk hvis de mangler.

## 7. Gi andre tilgang til chat

Del URL til API-et bak reverse proxy (anbefalt HTTPS):
- `GET /health`
- `POST /v1/chat`
- `POST /v1/chat/stream`

## 8. Minimum sikkerhet i produksjon

- Eksponer ikke PostgreSQL-port `5432` offentlig.
- Sett opp HTTPS (Nginx/Caddy).
- Legg rate limiting på chat-endepunkter.
- Rotér `ADMIN_API_KEY` og `LLM_API_KEY` ved behov.
