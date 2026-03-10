#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/docker/.env.vps.multi"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.vps.yml"
SERVICE="rag_innovasjon_api"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${RAG_INNOVASJON_API_PORT:-8101}/health}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build --no-deps "$SERVICE"

for _ in $(seq 1 60); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "innorag healthy"
    exit 0
  fi
  sleep 2
done

echo "innorag did not become healthy in time" >&2
exit 1
