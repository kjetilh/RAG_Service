# VPS Docker-oppsett (Hetzner Ubuntu 24.04)

Denne siden dokumenterer Docker-installasjonen på `89.167.90.101`.

## 1) Hva som er installert

- Docker Engine: `29.2.1`
- Docker Compose plugin: `v5.1.0`
- containerd: installert og aktiv
- buildx plugin: installert

Pakkekilde:

- Offisielt Docker apt-repo for Ubuntu (`download.docker.com`)

## 2) Tjenester og konfigurasjon

Systemd:

- `docker.service`: aktivert og startet
- `containerd.service`: aktivert og startet

Docker daemon config:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "live-restore": true
}
```

Fil:

- `/etc/docker/daemon.json`

## 3) Brukertilgang

- `ops` er medlem av `docker`-gruppen og kan kjøre Docker uten `sudo`.
- `haven` og `dimy` er ikke i `docker`-gruppen (bevisst minste privilegium).

## 4) Verifisering (kjørt)

Som root:

```bash
docker --version
docker compose version
systemctl is-active docker
```

Som ops:

```bash
su - ops -c 'docker --version && docker compose version && docker ps'
```

## 5) Anbefalt videre

- kjør all Docker-drift via `ops`
- hold `.env` secrets utenfor git
- vurder `unattended-upgrades` og `fail2ban` som neste hardeningsteg
