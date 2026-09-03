#!/usr/bin/env bash
set -Eeuo pipefail

: "${GREEN_MAIN_SHA:?GREEN_MAIN_SHA is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
[[ "$GREEN_MAIN_SHA" =~ ^[0-9a-f]{40}$ ]]
current_main="$(gh api "repos/${GITHUB_REPOSITORY}/commits/main" --jq .sha)"
[[ "$current_main" == "$GREEN_MAIN_SHA" ]]

required_checks=(container secrets validate certification-static)
checks_ready=false
for _ in $(seq 1 60); do
  checks="$(gh api "repos/${GITHUB_REPOSITORY}/commits/${GREEN_MAIN_SHA}/check-runs?per_page=100")"
  failed="$(jq -r --argjson required "$(printf '%s\n' "${required_checks[@]}" | jq -R . | jq -s .)" '
    [.check_runs[] | select(.name as $name | $required | index($name)) |
      select(.status == "completed" and (.conclusion | IN("success", "skipped", "neutral") | not))] | length
  ' <<<"$checks")"
  [[ "$failed" == 0 ]] || { echo "A required exact-SHA check failed." >&2; exit 1; }
  passed=true
  for name in "${required_checks[@]}"; do
    jq -e --arg name "$name" '.check_runs | any(.name == $name and .conclusion == "success")' \
      <<<"$checks" >/dev/null || passed=false
  done
  if [[ "$passed" == true ]]; then checks_ready=true; break; fi
  sleep 10
done
[[ "$checks_ready" == true ]] || { echo "Required exact-SHA checks did not complete." >&2; exit 1; }

intent_file=.release/intent.json
if [[ ! -f "$intent_file" ]]; then printf 'dispatched=false\n' >>"$GITHUB_OUTPUT"; exit 0; fi
git rev-parse HEAD^ >/dev/null
if git diff --quiet HEAD^ HEAD -- "$intent_file"; then
  echo "Release intent did not change in this exact protected-main commit."
  printf 'dispatched=false\n' >>"$GITHUB_OUTPUT"
  exit 0
fi
intent_outputs="$(mktemp)"
trap 'rm -f "$intent_outputs"' EXIT
python3 operations/validate_release_intent.py "$intent_file" "$GREEN_MAIN_SHA" "$intent_outputs"
# shellcheck disable=SC1090
source "$intent_outputs"
if [[ "$enabled" != true ]]; then printf 'dispatched=false\n' >>"$GITHUB_OUTPUT"; exit 0; fi

existing="$(gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/deploy.yml/runs?event=workflow_dispatch&per_page=100" \
  --jq "[.workflow_runs[] | select(.head_sha == \"$GREEN_MAIN_SHA\")] | length")"
if [[ "$existing" != 0 ]]; then
  echo "A deployment run already exists for this exact intent commit."
  printf 'dispatched=false\n' >>"$GITHUB_OUTPUT"
  exit 0
fi

gh api --method POST "repos/${GITHUB_REPOSITORY}/actions/workflows/deploy.yml/dispatches" \
  -f ref=main \
  -f "inputs[source_sha]=$source_sha" \
  -f "inputs[target]=$target" \
  -f "inputs[publish_images]=$publish_images" \
  -f "inputs[backend_image]=$backend_image" \
  -f "inputs[edge_image]=$edge_image" \
  -f "inputs[deploy]=$deploy" \
  -f "inputs[change_id]=$change_id" \
  -f "inputs[allow_schema_migrations]=$allow_schema_migrations" \
  -f "inputs[migration_compatibility_approved]=$migration_compatibility_approved"

jq -n --arg dispatcher_sha "$GREEN_MAIN_SHA" --arg source_sha "$source_sha" \
  --arg target "$target" --arg change_id "$change_id" \
  --arg dispatched_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{schema_version:1,dispatcher_sha:$dispatcher_sha,source_sha:$source_sha,target:$target,change_id:$change_id,dispatched_at:$dispatched_at,deployment_read_only:true,live_effects_authorized:false}' \
  > dispatch-evidence.json
printf 'dispatched=true\n' >>"$GITHUB_OUTPUT"
