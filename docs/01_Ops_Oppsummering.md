# Oppsummering: RAG-service + install/ops (basert på denne chatten)

Dette dokumentet oppsummerer hva vi har bygget opp, hvilke problemer som oppstod og ble fikset, og hvilke kommandoer du bruker for å kjøre hele stacken lokalt.

## 1) Hva vi har nå

### RAG-service (Python/FastAPI)
Repoet `rag_service_repo_plus` inneholder en kjørbar RAG-service med:

- **FastAPI API-server**
  - `POST /v1/chat` (JSON-svar)
  - `POST /v1/chat/stream` (SSE streaming: `citations` → `delta` → `done`)
  - `POST /v1/admin/rebuild` (rebuild DB schema)
  - `POST /v1/admin/ingest` (ingest via API)
  - `GET /health`

- **Postgres + pgvector**
  - Tabeller: `documents`, `chunks`, `embeddings`
  - Indekser:
    - GIN på fulltekstsøk (`content_tsv`)
    - ivfflat på embeddings (`vector_cosine_ops`)

- **Ingest-pipeline**
  - Leser filer fra mappe (md/txt; html/pdf/docx støttes ved ekstra deps)
  - Cleaner → chunker → lagrer chunks → lager embeddings → lagrer embeddings i pgvector

- **Retrieval**
  - Hybrid:
    - Lexical: Postgres full-text search
    - Vector: pgvector cosine search
  - Dedupe + context packing (maks chunks per dokument)

- **Query rewrite (valgfritt)**
  - Omskriver spørsmål via LLM for bedre retrieval (`QUERY_REWRITE_ENABLED=true`)

- **Reranker (valgfritt)**
  - Cross-encoder reranking (krever `sentence-transformers` + `torch`)
  - Slås på med `RERANKER_ENABLED=true`

- **Streng grounding gate**
  - Krever at hvert avsnitt har `[n]`-henvisninger og at indeksene er gyldige
  - Styrt av `GROUNDING_MIN_CITATIONS`

### Swift-klient (CLI)
Du har en Swift Package CLI-klient (`SwiftRAGClient`) som støtter:
- `json` modus (kaller `/v1/chat`)
- `stream` modus (kaller `/v1/chat/stream` og printer citations + streaming tekst)

## 2) Hva vi installerte / endret underveis (ifølge chatten)

### Python / venv
- Vi endte på **Python 3.11** (Homebrew). Dette var viktig fordi enkelte pakker (spesielt torch) ofte feiler på “feil” Python-versjon/plattform.

### Postgres-driver (SQLAlchemy)
- Du fikk `ModuleNotFoundError: psycopg2` i starten.
- Vi gikk for **psycopg v3** og måtte:
  - Installere (zsh krever quoting pga `[]`):
    - `pip install 'psycopg[binary]'`
  - Sørge for at SQLAlchemy bruker psycopg v3 ved å sette:
    - `DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/ragdb`

### Torch-problemet
- Du fikk “torch ikke installert” og ved install fikk du “no versions found”.
- Typiske årsaker: Python-versjon, plattform, pip-index.
- Vi diskuterte:
  - macOS CPU install via PyTorch wheel index:
    - `pip install torch --index-url https://download.pytorch.org/whl/cpu`
  - eller bare kjøre uten reranker:
    - `RERANKER_ENABLED=false` (RAG fungerer fint uten torch)

### Lokal Postgres-instans kolliderte med Docker
- Du fant en lokal Postgres-instans som allerede brukte port 5432.
- Når den ble fjernet, fungerte Docker Postgres som forventet.

### “role rag does not exist”
- Oppstår når DB/volume ikke er initialisert med forventet bruker.
- Løsningen i dev er ofte å resette volumet:
  - `docker compose down -v` (sletter data) og start på nytt.

### SQL-feil ved embeddings insert
- Du fikk SQL-feil rundt `:embedding::vector`.
- Fiksen som fungerte i `vector_store.py`:
  - Bruk `CAST(:embedding AS vector)` i stedet for `:embedding::vector` for robust parameter-parsing i SQLAlchemy `text()`.

## 3) Docker: starte/stopp/resette Postgres

Fra repo-mappa:

### Start DB
```bash
docker compose -f docker/docker-compose.yml up -d db
```

### Sjekk at den kjører
```bash
docker ps
```

### Stopp DB
```bash
docker compose -f docker/docker-compose.yml down
```

### Full reset (sletter volum/data; nyttig ved feil roller/db)
```bash
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d db
```

## 4) psql: gå inn i databasen

Koble til (fra host-maskinen):
```bash
psql postgresql://rag:rag@localhost:5432/ragdb
```

Nyttige `psql`-kommandoer:
```sql
\dt            -- list tabeller
\dx            -- list extensions (sjekk pgvector)
SELECT COUNT(*) FROM documents;
SELECT COUNT(*) FROM chunks;
SELECT COUNT(*) FROM embeddings;
\q             -- avslutt
ragdb=# \copy documents to '<path_to>/filename.csv' CSV HEADER
```

## 5) Rebuild schema (opprette tabeller/index)

Når DB kjører:
```bash
source .venv/bin/activate
python -m scripts.rebuild_index
```

## 6) Ingest dokumenter

Eksempel (som i chatten):
```bash
python -m scripts.ingest_folder --path ../papers --source-type paper --author "Test" --year 2024
```

## 7) Starte API-server

```bash
uvicorn app.main:app --reload --port 8000
```

Test:
```bash
curl http://localhost:8000/health
```

Chat test:
```bash
curl -X POST http://localhost:8000/v1/chat   -H "Content-Type: application/json"   -d '{"message":"Hva er innovasjonspolitiske virkemidler?"}'
```

## 8) Swift-klient (kort)

I `SwiftRAGClient`-mappa:
```bash
swift build -c release
.build/release/SwiftRAGClient http://localhost:8000 stream "Hva er innovasjonspolitiske virkemidler?"
```
