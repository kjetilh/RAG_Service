# InnoRAG Bokskriving Runbook

Dette dokumentet beskriver hvordan `innorag` kan brukes som skrivehjelp for innovasjonsledelse-boka med bade artikler og intervju-transkripsjoner.

## Status na

Det som allerede finnes i repoet:

- `innovasjon`: case for artikler og fagstoff
- `innovasjon_intervjuer`: case for intervju-transkripsjoner
- `POST /v1/interviews/collective-summary`: kollektiv analyse per fast sporsmalssett
- `innovasjon_bokskriving`: nytt kombinert case for artikler + intervjuer

## Anbefalt bruksmønster

Bruk tre arbeidsflater:

1. `innovasjon`
   - nar du vil ha litteratur- og faggrunnlag alene
2. `innovasjon_intervjuer`
   - nar du vil analysere intervjuene alene
3. `innovasjon_bokskriving`
   - nar du vil ha skrivehjelp som kombinerer artikler og intervjuer

## Intervju-sporsmalssett

For innovasjonspolitikk og virkemidler finnes et dedikert sporsmalssett:

- `config/interview_questions_innovasjonspolitikk.yml`

Bruk det sammen med:

- `case_id=innovasjon_intervjuer`
- `source_type=innovasjon_intervju_transcript`

## Intervju-transkripsjoner

Lokal mappe oppgitt for dette bokprosjektet:

- `/Users/kjetil/Documents/Bokprosjekt_Innovasjonsledelse/interviews`

Disse filene bor ingestes eller synkes med:

- `source_type=innovasjon_intervju_transcript`

## Eksempel: sync intervju-mappe

```bash
curl -s -X POST http://127.0.0.1:8101/v1/admin/sync \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $RAG_INNOVASJON_ADMIN_API_KEY" \
  -d '{
    "path": "intervjuer/live",
    "source_type": "innovasjon_intervju_transcript",
    "delete_missing": true
  }'
```

Merk:

- `path` ma peke til en mappe under `INGEST_ROOT` pa serveren
- den lokale macOS-stien ma derfor kopieres eller sync-es inn til innorag sin uploads-mappe for serverbruk

## Eksempel: kollektiv analyse per sporsmal

```bash
curl -s -X POST http://127.0.0.1:8101/v1/interviews/collective-summary \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "innovasjon_intervjuer",
    "question_set_path": "config/interview_questions_innovasjonspolitikk.yml",
    "filters": {
      "source_type": ["innovasjon_intervju_transcript"]
    },
    "top_k": 12
  }'
```

Dette gir en per-sporsmal-oppsummering pa tvers av intervjuene.

## Eksempel: skrivehjelp med kombinert case

```bash
curl -s -X POST http://127.0.0.1:8101/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "innovasjon_bokskriving",
    "query": "Lag en struktur for et bokavsnitt om innovasjonspolitikk og virkemidler, basert pa bade litteraturen og intervjuene. Skill tydelig mellom litteraturgrunnlag, intervjufunn og inferens.",
    "top_k": 12
  }'
```

## Valgfri promptprofil for bokskriving

Hvis du vil sette `innorag` i en tydeligere bokskrivingsmodus, finnes disse filene:

- `prompts/system_persona_bokskriving.md`
- `prompts/answer_template_bokskriving.md`

Viktig:

- promptvalg i dagens tjeneste er runtime-globalt per instans, ikke per case
- hvis du bytter disse inn pa `innorag`, gjelder det hele innovasjonstjenesten til du bytter tilbake

## Begrensning na

Den viktigste begrensningen er at promptprofil ikke velges automatisk per case. Det betyr:

- case-seleksjon er per request
- promptprofil er fortsatt per instans

For ren bokskriving er dette likevel ofte akseptabelt hvis `innorag` primart brukes til bokprosjektet.
