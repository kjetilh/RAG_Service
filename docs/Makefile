# Minimal Makefile for rag_service_repo_plus
# Usage examples:
#   make db-up
#   make rebuild
#   make ingest PAPERS=../papers
#   make api
#   make psql

PY?=python
DOCKER_COMPOSE?=docker compose -f docker/docker-compose.yml
PAPERS?=../papers
SOURCE_TYPE?=paper
AUTHOR?=Test
YEAR?=2024
PORT?=8000

.PHONY: help venv deps db-up db-down db-reset rebuild ingest api health psql counts

help:
	@echo "Targets:"
	@echo "  venv        - create venv (.venv) using python3.11"
	@echo "  deps        - install deps (editable) + psycopg[binary]"
	@echo "  db-up       - start postgres (docker)"
	@echo "  db-down     - stop postgres"
	@echo "  db-reset    - stop + delete volume (DANGEROUS: deletes data)"
	@echo "  rebuild     - create schema/indexes"
	@echo "  ingest      - ingest documents from PAPERS (default: ../papers)"
	@echo "  api         - run fastapi (uvicorn)"
	@echo "  health      - curl health"
	@echo "  psql        - open psql shell"
	@echo "  counts      - show table counts via psql"
	@echo ""
	@echo "Variables:"
	@echo "  PAPERS=$(PAPERS) SOURCE_TYPE=$(SOURCE_TYPE) AUTHOR=$(AUTHOR) YEAR=$(YEAR) PORT=$(PORT)"

venv:
	python3.11 -m venv .venv

deps:
	. .venv/bin/activate && $(PY) -m pip install -U pip
	. .venv/bin/activate && $(PY) -m pip install -e .
	. .venv/bin/activate && $(PY) -m pip install 'psycopg[binary]'

db-up:
	$(DOCKER_COMPOSE) up -d db

db-down:
	$(DOCKER_COMPOSE) down

db-reset:
	$(DOCKER_COMPOSE) down -v
	$(DOCKER_COMPOSE) up -d db

rebuild:
	. .venv/bin/activate && $(PY) -m scripts.rebuild_index

ingest:
	. .venv/bin/activate && $(PY) -m scripts.ingest_folder --path $(PAPERS) --source-type $(SOURCE_TYPE) --author "$(AUTHOR)" --year $(YEAR)

api:
	. .venv/bin/activate && uvicorn app.main:app --reload --port $(PORT)

health:
	curl -s http://localhost:$(PORT)/health && echo ""

psql:
	psql postgresql://rag:rag@localhost:5432/ragdb

counts:
	psql postgresql://rag:rag@localhost:5432/ragdb -c "SELECT 'documents' AS t, COUNT(*) FROM documents UNION ALL SELECT 'chunks', COUNT(*) FROM chunks UNION ALL SELECT 'embeddings', COUNT(*) FROM embeddings;"
