# Verifisering av `dimy_prompts`

Dette dokumentet beskriver et lite verifiseringssett for det brukerrettede komposisjonsverktøyet `dimy_prompts`.

Målet er å oppdage regresjoner i:

- casevalg
- svarform
- kildetype
- dokumenterte arbeidsromsoppskrifter

## Planfil

Bruk:

- `config/dimy_prompts_verification_plan.yml`

Planen dekker foreløpig:

1. arbeidsrom med katalog, RAG og prompt-admin
2. brukerrettet dokumentasjonsarbeidsrom
3. valg mellom fast case og router
4. case-bytte for research-klienter

## Kjøring lokalt eller på server

Bruk den eksisterende runneren:

```bash
python -m scripts.run_innorag_verification \
  --base-url http://127.0.0.1:8102 \
  --plan config/dimy_prompts_verification_plan.yml \
  --output-md /tmp/dimy_prompts_verification.md \
  --output-json /tmp/dimy_prompts_verification.json \
  --fail-on-failures
```

Selv om scriptnavnet nevner `innorag`, er runneren generisk. Den kan brukes mot alle query-endepunkter som følger samme responsformat.

## Hva som regnes som pass

Hver sjekk ser på:

- `trace.answer_mode`
- `trace.source_strategy`
- minimum antall kilder
- påkrevde tekstbiter i svaret
- påkrevde `source_type`

For `dimy_prompts` skal minst disse forholdene holde:

- `answer_mode` skal være `workspace_recipe`
- `source_strategy` skal være `articles`
- `source_types_applied` skal inneholde `prompt_docs`

## Drift

På VPS bør denne verifiseringen kjøres etter docs-sync på samme måte som `innorag`-verifiseringen.

Hvis en sjekk feiler, bør sync-kjeden markeres som mislykket slik at regresjonen blir synlig med en gang.
