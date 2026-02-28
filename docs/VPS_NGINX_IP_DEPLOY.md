# VPS deploy med Nginx på IP (uten DNS)

Denne guiden beskriver oppsettet som er brukt på `89.167.90.101` før DNS er klar.

## 1) Nginx-oppsett

Mål:

- HTTP (`:80`) redirect til HTTPS
- HTTPS (`:443`) med self-signed cert for IP
- reverse proxy til to RAG-tjenester

Ruter:

- `https://89.167.90.101/innovasjon/*` -> `127.0.0.1:8101/*`
- `https://89.167.90.101/dimy/*` -> `127.0.0.1:8102/*`

HTTP redirect:

- `http://89.167.90.101` returnerer `301` med `Location: https://89.167.90.101/`

Merk:

- self-signed cert gir browser warning inntil DNS + offentlig CA er satt opp

## 2) Deploy-path på server

Repo deployes som `ops`-bruker i:

- `/srv/ops/rag_service`

Compose-fil:

- `docker/docker-compose.vps.yml`

Miljøfil:

- `docker/.env.vps.multi`

## 3) Runtime-status (verifisert)

Direkte health:

- `http://127.0.0.1:8101/health` -> `{"ok":true}`
- `http://127.0.0.1:8102/health` -> `{"ok":true}`

Via Nginx:

- `https://89.167.90.101/innovasjon/health` -> `{"ok":true}`
- `https://89.167.90.101/dimy/health` -> `{"ok":true}`

## 4) Chat-test

`/v1/chat` er oppe, men krever `LLM_API_KEY`.

Nåværende respons:

- `500` med `LLM_API_KEY is empty. Set it in .env (LLM_API_KEY=...)`

Dette er forventet til gyldige LLM-nøkler settes i:

- `RAG_INNOVASJON_LLM_API_KEY`
- `RAG_DIMY_LLM_API_KEY`

## 5) Neste steg når DNS er klar

- sett opp A/AAAA-record
- bytt self-signed cert til Let's Encrypt/ACME i Nginx
- behold samme proxy-ruter for `innovasjon` og `dimy`
