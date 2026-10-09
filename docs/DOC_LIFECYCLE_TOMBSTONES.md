# Document Lifecycle, doc_state og Tombstones

Dette dokumentet beskriver hvordan dokumentlivslopet fungerer i dagens sync-implementasjon.

## Document state

Dokumenter har disse state-verdiene:

- `active`
- `tombstone_pending`
- `tombstone`

I tillegg finnes:

- `doc_version`
- `replaced_by_doc_id`
- `state_reason`
- `tombstoned_at`
- `updated_at`

## Nar brukes dette

Denne logikken brukes i `sync`-flyten, ikke i vanlig `ingest`.

- `POST /v1/admin/ingest`: batch-ingest
- `POST /v1/admin/sync`: synk av live-mapper

## Hovedregler

### 1. Ny fil

- filen hashes
- hvis filen ikke finnes fra for, opprettes nytt dokument

### 2. Uendret fil

- hvis innholdshash matcher eksisterende dokument for samme filsti, beholdes dokumentet
- hvis et matchende dokument ikke er `active`, reaktiveres det i tombstone-mode

### 3. Endret fil

- ny hash gir nytt `doc_id`
- gammel versjon for samme filsti blir enten:
  - hard-slettet hvis tombstone-mode er av
  - satt til `tombstone` med `state_reason=replaced_by_new_version` hvis tombstone-mode er pa

### 4. Fil fjernet fra kilden

Ved `delete_missing=true`:

- uten tombstone-mode: dokumentet slettes hardt
- med tombstone-mode:
  - forst `tombstone_pending`
  - etter grace-periode: `tombstone`

## Anti-thrash

Tombstone-mode bruker to mekanismer for a unnga aggressiv sletting:

1. `tombstone_grace_seconds`
   - hvor lenge et dokument kan vaere `tombstone_pending` for det blir `tombstone`
2. `anti_thrash_batch_size`
   - batchstorrelse for state-overganger

Dette er laget for a handtere kortvarige sync-avvik, repo-endringer og midlertidig manglende filer uten hard delete med en gang.

## Praktisk semantikk for `delete_missing`

`delete_missing=true` betyr ikke alltid hard delete.

I next-gen/tombstone-mode betyr det:

- sammenlign live-kilden med indeksen
- dokumenter som ikke lenger finnes i kilden markeres som `tombstone_pending`
- etter grace-periode markeres de som `tombstone`

Hard delete brukes bare nar tombstone-mode er av.

## Case- og corpus-visning

- `corpus`-endepunkter skjuler tombstones som default
- `include_tombstones=true` viser dem
- research download tillater bare `active` dokumenter

## Begrensninger na

- lifecycle er dokumentert i kode og runbooks, men ikke i en egen operativ kontrakt utenfor repoet
- tombstone/evaluation/case-lifecycle er ikke knyttet til et separat admin-UI ennå
- det finnes ikke et eget audit-endepunkt som viser state-overganger per dokument
