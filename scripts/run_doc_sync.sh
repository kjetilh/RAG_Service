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

# The repos under /srv/ops/repos are read-only mirrors that documentation is
# exported from. `git pull --ff-only` stops working the day upstream history is
# rewritten or the mirror sits on a detached HEAD; that happened 2026-05-05 and
# the documentation RAG served five-month-old docs until 2026-10-08, while each
# source still reported "ok". A mirror therefore follows origin: fast-forward
# when possible, otherwise keep the old tip under a tag and move to origin.
# A mirror with local modifications is left alone and counted as a failure.
update_mirror() {
  local repo="$1" branch target
  branch="$(git -C "$repo" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')"
  if [ -z "$branch" ]; then
    branch="$(git -C "$repo" symbolic-ref -q --short HEAD 2>/dev/null || true)"
  fi
  if [ -z "$branch" ]; then
    if git -C "$repo" rev-parse -q --verify origin/main >/dev/null; then branch=main; else branch=master; fi
  fi
  target="origin/$branch"
  git -C "$repo" rev-parse -q --verify "$target" >/dev/null || { echo "no $target in $repo" >&2; return 1; }
  if ! git -C "$repo" diff --quiet || ! git -C "$repo" diff --cached --quiet; then
    echo "mirror $repo has local modifications; not touching it" >&2
    return 1
  fi
  if [ "$(git -C "$repo" rev-parse HEAD)" = "$(git -C "$repo" rev-parse "$target")" ] \
     && [ "$(git -C "$repo" symbolic-ref -q --short HEAD 2>/dev/null)" = "$branch" ]; then
    return 0
  fi
  if git -C "$repo" merge-base --is-ancestor HEAD "$target"; then
    git -C "$repo" checkout -q -B "$branch" "$target"
    return $?
  fi
  local tag="mirror-before-reset-$(date -u +%Y%m%dT%H%M%SZ)"
  git -C "$repo" tag "$tag" HEAD || return 1
  echo "mirror $repo diverged from $target; old tip kept as tag $tag"
  git -C "$repo" checkout -q -B "$branch" "$target"
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
  if ! update_mirror "$repo"; then
    echo "mirror update failed for $repo" >&2
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
