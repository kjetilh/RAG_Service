# Kjør alt (lokal dev)

Dette er en “fra null til kjørende” sjekkliste for `rag_service_repo_plus`.

## 0) Forutsetninger
- Docker Desktop (eller Docker Engine)
- Python 3.11
- (valgfritt) `psql` klienten installert lokalt for å gå inn i DB

## 1) Opprett og aktiver venv + installer deps
Kjør fra repo-roten:

```bash
python3.11 -m venv .venv
source .venv/bin/activate

python -m pip install -U pip
python -m pip install -e .
python -m pip install 'psycopg[binary]'
```

Valgfritt (embeddings/reranker deps):
```bash
python -m pip install -e '.[emb]'
```

Valgfritt (loaders for pdf/html/docx):
```bash
python -m pip install -e '.[pdf,html,docx]'
```

## 2) Konfigurer .env
```bash
cp .env.example .env
```

Sjekk at denne er riktig (psycopg v3):
```env
DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/ragdb
```

## 3) Start Postgres (Docker)
```bash
docker compose -f docker/docker-compose.yml up -d db
```

Hvis du mistenker at et gammelt volum ligger igjen:
```bash
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d db
```

## 4) Rebuild DB schema
```bash
python -m scripts.rebuild_index
```

## 5) Ingest dokumenter
Eksempel:
```bash
python -m scripts.ingest_folder --path ../papers --source-type paper --author "Test" --year 2024
```

## 6) Start API
```bash
uvicorn app.main:app --reload --port 8000
```

## 7) Test API
```bash
curl http://localhost:8000/health
```

```bash
curl -X POST http://localhost:8000/v1/chat   -H "Content-Type: application/json"   -d '{"message":"Oppsummer hovedtypene innovasjonsvirkemidler"}'
```

## 8) Test streaming (SSE)
Siden SSE er litt kjipt i `curl`, er det enklest å teste med Swift-klienten.

## 9) Gå inn i DB med psql
```bash
psql postgresql://rag:rag@localhost:5432/ragdb
```

Inne i psql:
```sql
\dt
\dx
SELECT COUNT(*) FROM documents;
SELECT COUNT(*) FROM chunks;
SELECT COUNT(*) FROM embeddings;
\q
```
