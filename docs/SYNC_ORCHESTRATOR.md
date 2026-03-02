# Sync Orchestrator for Dokumentasjons-RAG

Mål: holde dokumentasjon i flere repoer synkron med dokumentasjons-RAG (`rag_dimy_api`).

Orchestratoren gjør to ting per kilde:

1. Speiler filer fra repo -> live-mappe under `INGEST_ROOT`.
2. Kaller `POST /v1/admin/sync` for akkurat den live-mappen.

Til slutt henter den `GET /v1/admin/coverage-actions` for kvalitetskontroll.

## 1) Konfigurer

Kopier eksempel:

```bash
mkdir -p config
cp config/sync_orchestrator.example.toml config/sync_orchestrator.toml
```

Sett riktige `repo_path`-verdier og `source_type` for hver kilde.

Viktig:

- `ingest_root` skal være host-mappen som er mountet til `/data/uploads` i `rag_dimy_api`.
- `admin_base_url` skal peke til dokumentasjons-RAG (`http://127.0.0.1:8102` i nåværende oppsett).
- API-nøkkel leses fra env-variabel (`admin_api_key_env`).

## 2) Kjør manuelt

Last inn env og kjør plan:

```bash
set -a
. docker/.env.vps.multi
set +a
python -m scripts.sync_orchestrator --config config/sync_orchestrator.toml --plan-only
```

Kjør sync dry-run mot API:

```bash
python -m scripts.sync_orchestrator --config config/sync_orchestrator.toml --sync-dry-run
```

Kjør full sync:

```bash
python -m scripts.sync_orchestrator --config config/sync_orchestrator.toml
```

## 3) Automatisk kjøring (systemd timer)

Eksempel servicefil `/etc/systemd/system/rag-sync-orchestrator.service`:

```ini
[Unit]
Description=RAG sync orchestrator (docs -> doc RAG)
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/srv/ops/rag_service
User=ops
Group=ops
EnvironmentFile=/srv/ops/rag_service/docker/.env.vps.multi
ExecStart=/usr/bin/python3 -m scripts.sync_orchestrator --config /srv/ops/rag_service/config/sync_orchestrator.toml
```

Eksempel timer `/etc/systemd/system/rag-sync-orchestrator.timer`:

```ini
[Unit]
Description=Run RAG sync orchestrator every 30 minutes

[Timer]
OnBootSec=5m
OnUnitActiveSec=30m
Unit=rag-sync-orchestrator.service

[Install]
WantedBy=timers.target
```

Aktiver:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rag-sync-orchestrator.timer
sudo systemctl status rag-sync-orchestrator.timer
```

Se siste kjøring:

```bash
journalctl -u rag-sync-orchestrator.service -n 200 --no-pager
```
