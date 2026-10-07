# RAG Cases Schema

Dette dokumentet beskriver schema og semantikk for case-konfigurasjonen i `config/rag_cases.yml`.

## Status na

Repoet bruker i dag en enkelt YAML-fil:

- `config/rag_cases.yml`

Det finnes ikke en implementert loader for `rag_cases/*.yaml` i dagens kode. `settings.rag_cases_path` peker mot en enkelt fil, og `load_rag_cases()` leser akkurat den filen.

## Top-level schema

```yaml
version: 1
default_case: dimy_docs
cases:
  - case_id: dimy_docs
    description: ...
    enabled: true
    planner:
      docs_source_types: [...]
      prompts_source_types: [...]
      docs_keywords: [...]
      prompt_keywords: [...]
      default_domain: docs
    retrieval:
      top_k_vector: 50
      top_k_lexical: 50
      top_k_final: 12
      max_chunks_per_doc: 3
    prompt_profile:
      system_persona_path: prompts/system_persona_dimy_developer.md
      answer_template_path: prompts/answer_template_dimy_developer.md
    evaluation:
      min_citations: 2
      min_unique_docs: 1
      min_avg_score: 0.0
      enforce: false
```

## Felt

### `version`

- heltall >= 1

### `default_case`

- `case_id` som brukes hvis request ikke angir case eksplisitt

### `cases`

- minst ett case
- duplikate `case_id` er ikke tillatt

## Per-case felt

### `case_id`

- identifikator for case

### `description`

- fri tekst

### `enabled`

- hvis `false`, skal caset ikke brukes i case-lister eller research/cell-gateway

### `planner`

Brukes av den deterministiske next-gen planner-en.

- `docs_source_types`: source types som representerer dokumentasjon
- `prompts_source_types`: source types som representerer prompts
- `docs_keywords`: keywords for docs-domene
- `prompt_keywords`: keywords for prompt-domene
- `default_domain`: `docs` eller `prompts`

### `retrieval`

Brukes som retrieval-parametre i query-planen.

- `top_k_vector`
- `top_k_lexical`
- `top_k_final`
- `max_chunks_per_doc`

### `prompt_profile`

Valgfri per-case promptprofil.

- `system_persona_path`: systempersona for caset
- `answer_template_path`: svarmal for caset

Disse brukes når requesten velger caset direkte, eller når `prompt_profile_case_id` peker til caset.

### `evaluation`

Brukes av evaluation gate etter retrieval.

- `min_citations`
- `min_unique_docs`
- `min_avg_score`
- `enforce`

## Validering

Loaderen er streng:

- YAML med duplikate nøkler avvises
- ukjente felt avvises
- `default_case` ma finnes
- duplikate `case_id` avvises

## Aktuelle case i repoet

Per `config/rag_cases.yml` er disse definert:

- `dimy_docs`
- `dimy_prompts`
- `innovasjon`
- `innovasjon_intervjuer`
- `innovasjon_bokskriving`

## Operativ betydning

- `POST /v1/query` kan bruke `case_id`
- `POST /v1/retrieve` kan bruke `case_id`
- `POST /v1/research/query` krever `case_id`
- `POST /v1/research/retrieve` krever `case_id`
- `GET /v1/research/cases` og `GET /v1/cell/cases` bruker enabled cases fra denne filen

## Begrensninger na

- configen er ikke splittet i flere YAML-filer
- case-opprettelse er ikke produktisert som admin-endepunkt ennå
- evaluation gate er terskelbasert pa citations og score, ikke et fullverdig offline eval-sett
