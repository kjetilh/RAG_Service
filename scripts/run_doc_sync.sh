#!/usr/bin/env bash
set -euo pipefail

mkdir -p /srv/ops/rag_service/.run
exec 9>/srv/ops/rag_service/.run/rag-doc-sync.lock
if ! flock -n 9; then
  echo "Another rag doc sync run is already active"
  exit 0
fi

export HOME=/home/ops
cd /srv/ops/rag_service

if [ -f docker/.env.vps.multi ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|\#*) continue ;;
    esac
    key="${line%%=*}"
    value="${line#*=}"
    export "$key=$value"
  done < docker/.env.vps.multi
fi

mkdir -p logs/sync_orchestrator logs/innorag_verification logs/dimy_prompts_verification

repo_failures=0
rag_service_repo_changed=0
rag_service_redeploy_required=0
force_rag_service_deploy="${FORCE_RAG_SERVICE_DEPLOY:-0}"
auto_redeploy_rag_service="${AUTO_REDEPLOY_RAG_SERVICE:-0}"

rag_service_requires_redeploy() {
  local repo="$1"
  local before_rev="$2"
  local after_rev="$3"
  local changed_files

  if [ -z "$before_rev" ] || [ -z "$after_rev" ] || [ "$before_rev" = "$after_rev" ]; then
    return 1
  fi

  changed_files="$(git -C "$repo" diff --name-only "$before_rev" "$after_rev" || true)"
  if [ -z "$changed_files" ]; then
    return 1
  fi

  while IFS= read -r path; do
    case "$path" in
      app/*|scripts/*|config/*|prompts/*|docker/*|pyproject.toml|uv.lock|requirements*.txt|constraints*.txt)
        return 0
        ;;
    esac
  done <<< "$changed_files"

  return 1
}

for repo in /srv/ops/repos/*; do
  [ -d "$repo/.git" ] || continue
  repo_name="$(basename "$repo")"
  before_rev="$(git -C "$repo" rev-parse HEAD 2>/dev/null || true)"
  echo "Updating $repo_name"
  if ! git -C "$repo" fetch --prune origin; then
    echo "git fetch failed for $repo" >&2
    repo_failures=$((repo_failures + 1))
    continue
  fi
  if ! git -C "$repo" pull --ff-only; then
    echo "git pull failed for $repo" >&2
    repo_failures=$((repo_failures + 1))
    continue
  fi
  after_rev="$(git -C "$repo" rev-parse HEAD 2>/dev/null || true)"
  if [ "$repo_name" = "RAG_Service" ] && [ -n "$before_rev" ] && [ "$before_rev" != "$after_rev" ]; then
    rag_service_repo_changed=1
    if rag_service_requires_redeploy "$repo" "$before_rev" "$after_rev"; then
      rag_service_redeploy_required=1
      echo "RAG_Service changed in runtime-relevant paths; redeploy is required"
    else
      echo "RAG_Service changed, but only in non-runtime paths; skipping redeploy trigger"
    fi
  fi
done

if git -C /srv/ops/rag_service rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if git -C /srv/ops/rag_service diff --quiet && git -C /srv/ops/rag_service diff --cached --quiet; then
    echo "Updating rag_service"
    if ! git -C /srv/ops/rag_service fetch --prune origin; then
      echo "git fetch failed for /srv/ops/rag_service" >&2
      repo_failures=$((repo_failures + 1))
    elif ! git -C /srv/ops/rag_service pull --ff-only; then
      echo "git pull failed for /srv/ops/rag_service" >&2
      repo_failures=$((repo_failures + 1))
    fi
  else
    echo "Skipping git pull for /srv/ops/rag_service because the worktree is dirty"
  fi
else
  echo "Skipping git pull for /srv/ops/rag_service because it is not a valid git worktree"
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
sync_log_dir=/srv/ops/rag_service/logs/sync_orchestrator
sync_log_path="$sync_log_dir/$timestamp.json"

python3 -m scripts.sync_orchestrator --config config/sync_orchestrator.toml | tee "$sync_log_path"
ln -sfn "$sync_log_path" "$sync_log_dir/latest.json"

if [ "$force_rag_service_deploy" = "1" ] || { [ "$auto_redeploy_rag_service" = "1" ] && [ "$rag_service_redeploy_required" -eq 1 ]; }; then
  echo "Redeploying rag services from repo mirror"
  SOURCE_ROOT=/srv/ops/repos/RAG_Service OPS_ROOT=/srv/ops/rag_service ./scripts/deploy_innorag.sh
  SOURCE_ROOT=/srv/ops/repos/RAG_Service OPS_ROOT=/srv/ops/rag_service ./scripts/deploy_doc.sh
elif [ "$auto_redeploy_rag_service" = "1" ] && [ "$rag_service_repo_changed" -eq 1 ]; then
  echo "AUTO_REDEPLOY_RAG_SERVICE=1, but no runtime-relevant RAG_Service changes were detected"
fi

verify_log_dir=/srv/ops/rag_service/logs/innorag_verification
verify_md="$verify_log_dir/$timestamp.md"
verify_json="$verify_log_dir/$timestamp.json"
python3 -m scripts.run_innorag_verification \
  --base-url "http://127.0.0.1:${RAG_INNOVASJON_API_PORT:-8101}" \
  --plan config/innorag_verification_plan.yml \
  --output-md "$verify_md" \
  --output-json "$verify_json" \
  --fail-on-failures
ln -sfn "$verify_md" "$verify_log_dir/latest.md"
ln -sfn "$verify_json" "$verify_log_dir/latest.json"

prompt_verify_log_dir=/srv/ops/rag_service/logs/dimy_prompts_verification
prompt_verify_md="$prompt_verify_log_dir/$timestamp.md"
prompt_verify_json="$prompt_verify_log_dir/$timestamp.json"
python3 -m scripts.run_innorag_verification \
  --base-url "http://127.0.0.1:${RAG_DIMY_API_PORT:-8102}" \
  --plan config/dimy_prompts_verification_plan.yml \
  --output-md "$prompt_verify_md" \
  --output-json "$prompt_verify_json" \
  --fail-on-failures
ln -sfn "$prompt_verify_md" "$prompt_verify_log_dir/latest.md"
ln -sfn "$prompt_verify_json" "$prompt_verify_log_dir/latest.json"

if [ "$repo_failures" -gt 0 ]; then
  echo "Completed sync with $repo_failures git update failures" >&2
  exit 1
fi
