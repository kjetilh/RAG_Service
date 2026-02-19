# Ingest: flytt filer til *_done / *_failed

Skriptet `scripts/ingest_folder.py` flytter nå filer etter ingest:

- Ved vellykket ingest flyttes filen til en søstermappe med suffiks `_done`
- Ved feil flyttes filen til en søstermappe med suffiks `_failed`

Eksempel:
- `--path ../papers` → flytter til `../papers_done/` eller `../papers_failed/`

Mapper opprettes automatisk. Relativ mappestruktur under `papers/` bevares.
