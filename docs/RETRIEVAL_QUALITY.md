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

Harness, same corpus and questions for every row. `no`/`en` = `doc@5` for the Norwegian and English questions.

| Variant | doc@1 | doc@5 | doc@12 | MRR | ans@12 | no | en | mh_all |
|---|---|---|---|---|---|---|---|---|
| Deployed logic until 2026-10-08 (v1 chunks, all-MiniLM, AND-lexical, max fusion) | 29.9 | 44.9 | 50.5 | 0.366 | 41.1 | 11.1 | 79.2 | 18.8 |
| **v2 chunks + multilingual MiniLM + BM25 + RRF** | 49.5 | 86.0 | 93.5 | 0.632 | 83.2 | 75.9 | 96.2 | 62.5 |
| **... + cross-encoder re-ranking (30 candidates)** | 75.7 | 89.7 | 95.3 | 0.821 | 84.1 | 85.2 | 94.3 | 75.0 |
| ... without title/heading context in the indexed text | 43.9 | 77.6 | 91.6 | 0.585 | 78.5 | 64.8 | 90.6 | 62.5 |
| ... smaller chunks (target 140 words) | 43.9 | 83.2 | 92.5 | 0.605 | 86.0 | 74.1 | 92.5 | 68.8 |
| ... larger chunks (target 320 words) | 47.7 | 75.7 | 89.7 | 0.589 | 83.2 | 63.0 | 88.7 | 68.8 |
| ... multilingual-e5-small instead (5x slower to index) | 47.7 | 70.1 | 81.3 | 0.569 | 76.6 | 46.3 | 94.3 | 50.0 |
| ... lexical weight 1.5 | 50.5 | 80.4 | 84.1 | 0.621 | 78.5 | 64.8 | 96.2 | 56.2 |
| ... vector weight 1.5 | 48.6 | 77.6 | 84.1 | 0.605 | 71.0 | 70.4 | 84.9 | 37.5 |
| ... 100 candidates per channel | 50.5 | 77.6 | 90.7 | 0.619 | 80.4 | 64.8 | 90.6 | 62.5 |
| ... max 2 chunks per document | 49.5 | 86.0 | 95.3 | 0.634 | 83.2 | 75.9 | 96.2 | 62.5 |
| ... link graph, reserved slots (2) | 49.5 | 86.0 | 90.7 | 0.629 | 81.3 | 75.9 | 96.2 | 68.8 |
| ... link graph, reserved slots (1) | 49.5 | 86.0 | 92.5 | 0.631 | 82.2 | 75.9 | 96.2 | 68.8 |
| ... link + shared-symbol graph, reserved slots (2) | 49.5 | 86.0 | 92.5 | 0.631 | 82.2 | 75.9 | 96.2 | 75.0 |
| ... link graph as a third ranking (personalised PageRank) | 47.7 | 76.6 | 90.7 | 0.611 | 77.6 | 68.5 | 84.9 | 62.5 |

On the larger corpus that also holds the private repositories (1341 files) the
order is the same: 40.2 -> 81.3 for `doc@5`; RRF alone (still AND-lexical) changes
nothing (40.2), BM25 + RRF on v1 chunks gives 59.8.

The running service, measured through its own retrieval code and over HTTPS
(`POST /v1/cases/dimy_docs/retrieve`), all 108 questions:

LIVE_TABLE

Six of the 108 questions have their answer in a chapter that is not on
`origin/main` (Book 33, 34 and 36 Agent Trust Package), so the service cannot
find them; "answerable" leaves those out. The harness numbers above are higher
than the live ones because the harness corpus used the working tree the
questions were written from.

## What is switched on for the documentation RAG

| Setting | Value | Why |
|---|---|---|
| `CHUNKER_VERSION` | `v2` | v1 keeps only the nearest heading, drops the text before the first heading and makes one chunk per section however small. v2 keeps the heading path, merges small sections and indexes `title > heading path` with the body. Indexing that context alone is worth 8 points of `doc@5` (77.6 -> 86.0). |
| `LEXICAL_MODE` | `bm25` | The Postgres `plainto_tsquery` channel ANDs every word of the question; for natural-language questions it returned nothing. |
| `HYBRID_FUSION` | `rrf` | With "largest raw score wins", a lexical score can never beat a cosine score. |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | all-MiniLM-L6-v2 is English-only: Norwegian questions found the right document in the top 5 in 11 % of the cases. Same vector size (384), so no schema change. |
| `VECTOR_EXACT_SEARCH` | `true` (default) | ivfflat with `probes=1` scans about 1 % of the vectors and filters afterwards. |
| `DOC_ID_SCHEME` | `v2` | v1 ids collide for same-name, same-content files in two folders; sync then moved the row back and forth every 30 minutes and tombstoned Book chapters. |

`EMBEDDING_MODEL`, `CHUNKER_VERSION` and `DOC_ID_SCHEME` are properties of an
index. Changing one means building a new database and switching to it.

## Measured and NOT switched on

- Link graph in combination with the hybrid ranking (`GRAPH_MODE=expand`, code in
  `app/rag/retrieve/graph_expand.py`). Three uses were measured:
  - as a third ranking (personalised PageRank from the top documents): worse on
    every measure (`doc@5` 86.0 -> 76.6);
  - reserved slots for documents linked from the top documents: `doc@5` is
    unchanged by construction; of 16 multi-hop questions one or two more get both
    documents (62.5 -> 68.8 / 75.0), and one to three of the 108 questions lose
    their document from the top 12 (93.5 -> 90.7 / 92.5);
  - with re-ranking on, the reserved slots changed nothing.
  That is too small and too mixed to switch on. What limits it is the
  documentation, not the code: the public corpus has 835 link edges over 607
  files, and whole chapters are not linked from anywhere (see
  `HAVEN-Deploy/_handoff/RAG/DOK-FUNN-20261008.md`, section 5).

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
