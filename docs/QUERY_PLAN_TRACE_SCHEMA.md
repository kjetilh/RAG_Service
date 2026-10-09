# Query Plan og Trace Schema

Dette dokumentet beskriver shape for `query_plan`, `trace` og `evaluation_gate` i dagens next-gen RAG.

## Hvor dette returneres

- `POST /v1/query`
- `POST /v1/research/query`
- `POST /v1/cell/cases/{case_id}/query`
- SSE fra `POST /v1/chat/stream` som `event: query_plan`

## `trace`

I `POST /v1/query` er `trace` et direkte speil av `retrieval_debug.query_plan`.

## `query_plan` felt

```json
{
  "planner_version": "ng-1",
  "planner_mode": "deterministic",
  "router_enabled": true,
  "selected_case": "dimy_docs",
  "requested_case": "dimy_docs",
  "selected_domain": "docs",
  "reason": "keyword_score",
  "source_types_applied": ["haven_docs", "cellprotocol_docs"],
  "matched_prompt_keywords": [],
  "matched_docs_keywords": ["api"],
  "prompt_keyword_hits": 0,
  "docs_keyword_hits": 1,
  "confidence": 1.0,
  "retrieval": {
    "top_k_vector": 50,
    "top_k_lexical": 50,
    "top_k_final": 12,
    "max_chunks_per_doc": 3
  }
}
```

## Feltforklaring

- `planner_version`: planner-kontraktversjon
- `planner_mode`: `deterministic` i next-gen, `legacy_router` i gammel sti
- `router_enabled`: om router/planner var aktiv
- `selected_case`: caset som faktisk ble brukt
- `requested_case`: caset requesten ba om, hvis noe
- `selected_domain`: `docs`, `prompts`, `mixed` eller `custom` avhengig av plannersti
- `reason`: hvorfor planneren valgte domene/filter
- `source_types_applied`: source_type-filter som faktisk ble sendt til retrieval
- `matched_prompt_keywords`: keywords som traff prompt-domene
- `matched_docs_keywords`: keywords som traff docs-domene
- `prompt_keyword_hits`: antall prompttreff
- `docs_keyword_hits`: antall docstreff
- `confidence`: enkel planner-confidence basert pa keyword-differanse
- `retrieval`: retrieval-parametre som faktisk ble brukt

## `evaluation_gate`

`retrieval_debug.evaluation_gate` inneholder:

```json
{
  "passed": true,
  "enforced": false,
  "thresholds": {
    "min_citations": 2,
    "min_unique_docs": 1,
    "min_avg_score": 0.0
  },
  "metrics": {
    "citation_count": 8,
    "unique_doc_count": 4,
    "avg_score": 0.58
  },
  "violations": []
}
```

## Viktig begrensning

Dette er ikke et fullverdig offline eval-rammeverk.

I dagens kode er evaluation gate bare en terskelsjekk over:

- antall citations
- antall unike dokumenter
- gjennomsnittlig retrieval-score

Det finnes ikke et innebygget eval-sett, golden answers eller regresjonsmatrise i runtime-pathen.
