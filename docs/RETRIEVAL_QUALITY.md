# Retrieval quality: what is measured, what is switched on, and why

Last verified against code and the running service: 2026-10-08.

## Purpose

A question about HAVEN/CellProtocol must bring back the section that answers it,
whether it is asked in Norwegian or English, and whether or not a language model
is available to formulate the answer. Every setting below exists because a
measurement showed it serves that purpose; settings that did not are listed too,
so they are not tried again without new evidence.

## How it is measured

- Question set: `eval/haven_docs_gold_v1.jsonl`, 108 questions (54 Norwegian, 54
  English; lookup, how-to, symbol, concept and 16 multi-hop questions). Each has
  the document(s) that answer it, the heading, and literal terms that the
  answering section contains.
- Harness: `scripts/eval_retrieval.py`. It loads a folder of documents, builds
  the index variants in memory and reports, per variant:
  - `doc@k`: the gold document is among the first k distinct documents
  - `ans@12`: a retrieved chunk from the gold document contains a gold term
  - `mh_all`: for multi-hop questions, both gold documents are in the result
- The running service is measured with the same questions through the retrieval
  code inside the container (`HAVEN-Deploy/_handoff/RAG/live_inside.py`), so the
  "before" and "after" numbers come from what users actually reach.

Run it (inside the service image, which has the models):

```bash
python scripts/eval_retrieval.py --corpus <folder with the docs> \
  --gold eval/haven_docs_gold_v1.jsonl --out results.json --cache /tmp/ragcache
```

`--stub` replaces the embedding model with a hashing embedder; use it only to
test the harness itself.

## Results (2026-10-08)

Corpus: the public repositories at `origin/main` that day (607 markdown files).

RESULTS_TABLE

## What is switched on for the documentation RAG

| Setting | Value | Why |
|---|---|---|
| `CHUNKER_VERSION` | `v2` | v1 produced chunks of 20-34 words on average and dropped the text before the first heading. v2 keeps the heading path, merges small sections and indexes `title > heading path` with the body. |
| `LEXICAL_MODE` | `bm25` | The Postgres `plainto_tsquery` channel ANDs every word of the question; for natural-language questions it returned nothing. |
| `HYBRID_FUSION` | `rrf` | With "largest raw score wins", a lexical score can never beat a cosine score. |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | all-MiniLM-L6-v2 is English-only: Norwegian questions found the right document in the top 5 in 11 % of the cases. Same vector size (384), so no schema change. |
| `VECTOR_EXACT_SEARCH` | `true` (default) | ivfflat with `probes=1` scans about 1 % of the vectors and filters afterwards. |
| `DOC_ID_SCHEME` | `v2` | v1 ids collide for same-name, same-content files in two folders; sync then moved the row back and forth every 30 minutes and tombstoned Book chapters. |

`EMBEDDING_MODEL`, `CHUNKER_VERSION` and `DOC_ID_SCHEME` are properties of an
index. Changing one means building a new database and switching to it.

## Measured and NOT switched on

GRAPH_SECTION

- Cross-encoder re-ranking: see the table. It costs seconds per question on the
  host's CPU.
- RRF weights (1.5x lexical or 1.5x vector), 100 candidates per channel instead
  of 50: all lower `doc@5`.

## Language model outage

If the provider answers "no credits" or rejects the key, the service does not
retry, remembers the failure for five minutes, and returns the ranked sources
with `retrieval_debug.generation_skipped = true` and the reason in
`generation_error`. Before 2026-10-08 the same situation made every question
wait about 95 seconds and end in HTTP 500 (from 2026-08-09 for the innovation
RAG; the documentation RAG had not answered a question since 2026-07-06).

Retrieval without a language model: `POST /v1/cases/{case_id}/retrieve`.

## Private sources

The public endpoint only holds documents from repositories that are public on
GitHub (`config/sync_orchestrator.doc_public.toml`). Documents from private
repositories (CellScaffold, DiMyMicropayments, DiMyMint, Sprout) are not in it.
They need an instance that is only reachable through an authenticated route
(`/v1/cell/...` behind the scaffold gateway, or the research API with tokens);
that instance is not set up yet.

## Rebuilding the index

1. Create a new database next to the current one.
2. Run the service image once against it with the new settings
   (`python -m scripts.rebuild_index`), then ingest every source with
   `scripts.sync_folder` (no HTTP timeout).
3. Measure the new index with the question set. Only then point the API at it.
4. Keep the old database until the new one has been in use for a while.

The scripts used on 2026-10-08 are in `HAVEN-Deploy/_handoff/RAG/`
(`rag-deploy-forbered.sh`, `rag-deploy-bytt.sh`, `rag-deploy-tilbake.sh`).
