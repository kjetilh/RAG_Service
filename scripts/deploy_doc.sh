#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/docker/.env.vps.multi"
COMPOSE_FILE="$ROOT_DIR/docker/docker-compose.vps.yml"
SERVICE="rag_dimy_api"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${RAG_DIMY_API_PORT:-8102}/health}"
COMPOSE_ARGS=(--env-file "$ENV_FILE" -f "$COMPOSE_FILE")
IMAGE_TAG="${IMAGE_TAG:-$(basename "$(dirname "$COMPOSE_FILE")")-${SERVICE}}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

DOCKER_BUILDKIT=0 docker build -t "$IMAGE_TAG" -f "$ROOT_DIR/docker/Dockerfile" "$ROOT_DIR"

container_id="$(docker compose "${COMPOSE_ARGS[@]}" ps -q "$SERVICE" || true)"
if [[ -n "$container_id" ]]; then
  docker stop "$container_id" >/dev/null 2>&1 || true
  docker rm -f "$container_id" >/dev/null 2>&1 || true
fi

docker compose "${COMPOSE_ARGS[@]}" up -d --no-deps "$SERVICE"

for _ in $(seq 1 60); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "doc healthy"
    exit 0
  fi
  sleep 2
done

docker compose "${COMPOSE_ARGS[@]}" logs --tail 80 "$SERVICE" >&2 || true
echo "doc did not become healthy in time" >&2
exit 1
