# rag-service (FastAPI + PostgreSQL/pgvector)

En enkel RAG-tjeneste laget som forskningsstøtte for bokprosjekt i innovasjonsledelse.

Dette repoet er ment som:
- et kjørbart eksempel på en RAG-pipeline
- et utgangspunkt for videre arbeid med en team-basert RAG-tjeneste
- et teknisk vedlegg som er lett å reprodusere lokalt og i sky

## Hva tjenesten gjør

- indekserer dokumenter fra filsystemet (MD, TXT, HTML, PDF, DOCX)
- lagrer chunks og embeddinger i PostgreSQL med pgvector
- kombinerer lexical søk og vectorsøk (hybrid retrieval)
- kan bruke query rewrite og reranking
- genererer svar via OpenAI-kompatibel API
- returnerer kilder (citations)
- støtter streaming via SSE

## Arkitektur i korte trekk

- API: FastAPI (`app/main.py`)
- Indeksering: `scripts/rebuild_index.py`
- Ingest: `scripts/ingest_folder.py`
- Retrieval/generering: `app/rag/*`
- Database: PostgreSQL + pgvector

## Viktige filer

- App Dockerfile: `docker/Dockerfile`
- Compose-oppsett (API + DB): `docker/docker-compose.yml`
- Miljøvariabler: `.env.example`
- SQL schema: `app/rag/index/schema.sql`
- VPS-guide: `docs/DEPLOY_VPS.md`

## PostgreSQL Dockerfile

Det finnes ikke en egen lokal Dockerfile for PostgreSQL i repoet.

PostgreSQL kjøres fra ferdig image:
- `pgvector/pgvector:pg16`
- definert i `docker/docker-compose.yml`

Dette er normalt oppsett for denne typen prosjekt.

## Forutsetninger

- Python 3.11
- Docker (Desktop eller Engine)
- valgfritt: `psql`

## Lokal kjøring (uten API i Docker)

1. Opprett og aktiver venv.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

2. Installer avhengigheter.

```bash
python -m pip install -U pip
python -m pip install -e .
```

Valgfritt for bedre ingest-formatstøtte:

```bash
python -m pip install -e '.[pdf,html,docx]'
```

Valgfritt for reranking:

```bash
python -m pip install -e '.[emb]'
```

3. Klargjør miljøfil.

```bash
cp .env.example .env
```

Sett minst:
- `LLM_API_KEY`
- `ADMIN_API_KEY`
- `DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/ragdb`

4. Start database i Docker.

```bash
docker compose -f docker/docker-compose.yml up -d db
```

5. Opprett schema/indexer.

```bash
python -m scripts.rebuild_index
```

6. Ingest dokumenter.

```bash
python -m scripts.ingest_folder --path ../papers --source-type paper --author "Test" --year 2024
```

7. Start API lokalt.

```bash
uvicorn app.main:app --reload --port 8000
```

## Docker kjøring (API + DB sammen)

1. Kopier miljøfil.

```bash
cp .env.example .env
```

2. Sett minst `LLM_API_KEY` og `ADMIN_API_KEY` i `.env`.

3. Start hele stacken.

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

4. Verifiser helse.

```bash
curl http://localhost:8000/health
```

## Ingest via opplastingsmappe i Docker

API-containeren får tilgang til `uploads/` i repoet via volume-mapping til `/data/uploads`.

Legg filer i f.eks. `uploads/team_docs/`, og kall admin-ingest:

```bash
curl -X POST http://localhost:8000/v1/admin/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <DIN_ADMIN_API_KEY>" \
  -d '{"path":"team_docs","source_type":"paper"}'
```

Merk:
- `path` må ligge under `INGEST_ROOT` (default `/data/uploads`).
- Ferdig prosesserte filer flyttes til `uploads/done/...`.
- Filer som feiler ingest flyttes til `uploads/failed/...`.
- `done/` og `failed/` opprettes automatisk hvis de mangler.
- Admin-endepunkter er deaktivert hvis `ADMIN_API_KEY` ikke er satt.

## API-endepunkter

- `GET /health`
- `POST /v1/chat`
- `POST /v1/chat/stream`
- `POST /v1/admin/rebuild` (krever `X-API-Key` + `{"confirm": true}`)
- `POST /v1/admin/ingest` (krever `X-API-Key`)

## Miljøvariabler du oftest justerer

- `DATABASE_URL`
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `ADMIN_API_KEY`
- `INGEST_ROOT`
- `QUERY_REWRITE_ENABLED`
- `RERANKER_ENABLED`
- `GROUNDING_MIN_CITATIONS`
- `STREAM_CHUNK_CHARS`

## Forslag for team-RAG videre

- legg inn auth og rollebasert tilgang foran API-et
- separer ingest-jobber fra online chat-API
- bruk managed PostgreSQL med pgvector i produksjon
- legg til observability (request logging, metrikker, tracing)
- legg til evalueringssett og regressjonstester for svar/kilder

## Git-klargjøring

Repoet er klart for:

```bash
git add .
git commit -m "Initial commit: rag-service baseline"
```

Deretter kan remote settes/pushes.
