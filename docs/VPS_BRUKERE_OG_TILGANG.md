# VPS brukere, grupper og tilgang (Hetzner)

Denne siden dokumenterer anbefalt praksis og faktisk oppsett gjort på `89.167.90.101`.

## 1) Anbefalt praksis for denne typen stack

For `scaffold + flere RAG` på én server:

- bruk dedikert admin-bruker for drift (`ops`) med `sudo`
- bruk egne prosjektbrukere (`haven`, `dimy`) uten `sudo`
- bruk separate prosjektkataloger under `/srv`
- gi kun brukere som må kjøre Docker medlemskap i `docker`-gruppen
- unngå host-installert PostgreSQL-bruker når DB kjører i Docker-container

Viktig:

- medlemskap i `docker`-gruppen er i praksis root-lignende tilgang
- derfor bør `haven` og `dimy` normalt ikke være i `docker`-gruppen

## 2) Hva som er satt opp på serveren

Opprettede grupper:

- `haven`
- `dimy`
- `ops`
- `docker` (forberedt for Docker-drift)

Opprettede brukere:

- `haven` (primærgruppe `haven`)
- `dimy` (primærgruppe `dimy`)
- `ops` (grupper: `ops`, `sudo`, `docker`)

Prosjektkataloger:

- `/srv/haven` eier `haven:haven` (mode `2770`)
- `/srv/dimy` eier `dimy:dimy` (mode `2770`)
- `/srv/ops` eier `ops:ops` (mode `2770`)

SSH-oppsett:

- `authorized_keys` er lagt inn for `haven`, `dimy` og `ops`
- lokal passordinnlogging for disse brukerne er låst (`passwd -l`)

## 3) Hvorfor vi ikke opprettet host-postgres-bruker

RAG-oppsettet kjører PostgreSQL som container (`pgvector/pgvector`).
Da håndteres DB-brukere i containeren og via miljøvariabler (`POSTGRES_*`), ikke som Linux-brukere på host.

## 4) Innloggingsmønster fremover

- bruk `ops` for drift og Docker/Compose
- bruk `haven` for HAVEN-filer og scripts
- bruk `dimy` for DiMy-filer og scripts

Eksempler:

```bash
ssh -i ~/.ssh/id_ed25519_hetzner ops@89.167.90.101
ssh -i ~/.ssh/id_ed25519_hetzner haven@89.167.90.101
ssh -i ~/.ssh/id_ed25519_hetzner dimy@89.167.90.101
```

## 5) Neste hardeningsteg (anbefalt)

- deaktiver root SSH-login etter at `ops` er verifisert i drift
- aktiver automatisk sikkerhetsoppdatering (`unattended-upgrades`)
- installer Docker Engine og Compose plugin
- legg på fail2ban for SSH
- bruk separate `.env`-filer per tjeneste med minst mulig secrets per bruker

## 6) Operativ policy (gjeldende fra 2026-02-26)

- daglig drift gjøres som `ops` (deploy, logs, docker compose, git pull)
- `root` brukes kun som break-glass for oppgaver som krever systemnivå:
  - pakkeinstallasjon
  - endring i `/etc/*`
  - systemd/SSH-hardening
- repoet under `/srv/ops/rag_service` eies av `ops:ops` for å unngå nye root-eide filer i vanlig drift
