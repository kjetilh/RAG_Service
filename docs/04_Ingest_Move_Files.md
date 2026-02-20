# Ingest: flytt filer til `done/` og `failed/`

Skriptet `scripts/ingest_folder.py` flytter filer etter ingest.

- Ved vellykket ingest flyttes filen til `done/`
- Ved feil flyttes filen til `failed/`
- Mappene opprettes automatisk hvis de mangler

## Standardoppsett i dette prosjektet

Når du bruker `INGEST_ROOT=/data/uploads` (Docker-oppsettet), får du:

- `/data/uploads/done/...`
- `/data/uploads/failed/...`

Siden `/data/uploads` er koblet til repoets `uploads/` på host, vil du typisk se:

- `uploads/done/...`
- `uploads/failed/...`

Relativ mappestruktur under input-path bevares.

Eksempel:
- input: `uploads/team_docs/kap1/notat.md`
- output ved suksess: `uploads/done/team_docs/kap1/notat.md`
- output ved feil: `uploads/failed/team_docs/kap1/notat.md`
