#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="${SOURCE_ROOT:-$ROOT_DIR}"
OPS_ROOT="${OPS_ROOT:-$ROOT_DIR}"
ENV_FILE="$OPS_ROOT/docker/.env.vps.multi"
COMPOSE_FILE="$OPS_ROOT/docker/docker-compose.vps.yml"
SERVICE="rag_innovasjon_api"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${RAG_INNOVASJON_API_PORT:-8101}/health}"
COMPOSE_ARGS=(--env-file "$ENV_FILE" -f "$COMPOSE_FILE")
IMAGE_TAG="${IMAGE_TAG:-$(basename "$(dirname "$COMPOSE_FILE")")-${SERVICE}}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

if [[ ! -f "$SOURCE_ROOT/docker/Dockerfile" ]]; then
  echo "Missing dockerfile: $SOURCE_ROOT/docker/Dockerfile" >&2
  exit 1
fi

DOCKER_BUILDKIT=0 docker build -t "$IMAGE_TAG" -f "$SOURCE_ROOT/docker/Dockerfile" "$SOURCE_ROOT"

container_id="$(docker compose "${COMPOSE_ARGS[@]}" ps -q "$SERVICE" || true)"
if [[ -n "$container_id" ]]; then
  docker stop "$container_id" >/dev/null 2>&1 || true
  docker rm -f "$container_id" >/dev/null 2>&1 || true
fi

docker compose "${COMPOSE_ARGS[@]}" up -d --no-deps "$SERVICE"

for _ in $(seq 1 60); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "innorag healthy"
    exit 0
  fi
  sleep 2
done

docker compose "${COMPOSE_ARGS[@]}" logs --tail 80 "$SERVICE" >&2 || true
echo "innorag did not become healthy in time" >&2
exit 1
