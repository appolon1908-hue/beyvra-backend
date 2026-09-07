#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEPLOY_RUN_ID:?DEPLOY_RUN_ID is required}"
: "${DEPLOY_HEAD_SHA:?DEPLOY_HEAD_SHA is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
[[ "$DEPLOY_RUN_ID" =~ ^[0-9]+$ ]]
[[ "$DEPLOY_HEAD_SHA" =~ ^[0-9a-f]{40}$ ]]

git fetch origin main
git cat-file -e "${DEPLOY_HEAD_SHA}^{commit}"
git merge-base --is-ancestor "$DEPLOY_HEAD_SHA" origin/main

rm -rf /tmp/beyvra-release
mkdir -p /tmp/beyvra-release
gh run download "$DEPLOY_RUN_ID" --repo "$GITHUB_REPOSITORY" \
  --pattern 'beyvra-backend-release-*' --dir /tmp/beyvra-release

mapfile -t manifests < <(
  find /tmp/beyvra-release -type f -name release-manifest.json -print
)
[[ "${#manifests[@]}" -eq 1 ]]
manifest="${manifests[0]}"
manifest_dir="$(dirname "$manifest")"
(
  cd "$manifest_dir"
  sha256sum -c release-manifest.json.sha256
)

source_sha="$(jq -r .source_sha "$manifest")"
backend_image="$(jq -r .backend_image "$manifest")"
edge_image="$(jq -r .edge_image "$manifest")"
target="$(jq -r .target "$manifest")"
change_id="$(jq -r .change_id "$manifest")"

[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]]
[[ "$backend_image" =~ ^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]]
[[ "$edge_image" =~ ^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]]
[[ "$change_id" =~ ^[A-Za-z0-9._-]+$ ]]
case "$target" in staging-readonly|production-readonly) ;; *) exit 1 ;; esac

git cat-file -e "${source_sha}^{commit}"
git merge-base --is-ancestor "$source_sha" origin/main
test "$source_sha" = "$DEPLOY_HEAD_SHA"

jq -e '
  .signed_build_verified == true and
  .deployment_read_only == true and
  .live_trading_authorized == false and
  .real_money_authorized == false and
  .payments_authorized == false and
  .withdrawals_authorized == false and
  .transactional_email_authorized == false and
  .external_execution_authorized == false
' "$manifest" >/dev/null

for evidence_name in \
  backend-build-attestation-verification.json \
  edge-build-attestation-verification.json; do
  evidence_path="$manifest_dir/$evidence_name"
  [[ -s "$evidence_path" ]]
  jq -e 'type == "array" and length > 0' "$evidence_path" >/dev/null
done

printf 'source_sha=%s\n' "$source_sha" >>"$GITHUB_OUTPUT"
printf 'backend_image=%s\n' "$backend_image" >>"$GITHUB_OUTPUT"
printf 'edge_image=%s\n' "$edge_image" >>"$GITHUB_OUTPUT"
printf 'target=%s\n' "$target" >>"$GITHUB_OUTPUT"
printf 'change_id=%s\n' "$change_id" >>"$GITHUB_OUTPUT"
