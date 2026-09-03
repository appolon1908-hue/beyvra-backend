#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEPLOY_RUN_ID:?DEPLOY_RUN_ID is required}"
: "${DEPLOY_HEAD_SHA:?DEPLOY_HEAD_SHA is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
[[ "$DEPLOY_HEAD_SHA" =~ ^[0-9a-f]{40}$ ]]

git fetch origin main
git merge-base --is-ancestor "$DEPLOY_HEAD_SHA" origin/main
mkdir -p /tmp/beyvra-release
gh run download "$DEPLOY_RUN_ID" --repo "$GITHUB_REPOSITORY" \
  --pattern 'beyvra-backend-release-*' --dir /tmp/beyvra-release
mapfile -t manifests < <(find /tmp/beyvra-release -type f -name release-manifest.json -print)
[[ "${#manifests[@]}" -eq 1 ]]
manifest="${manifests[0]}"
manifest_dir="$(dirname "$manifest")"
(cd "$manifest_dir" && sha256sum -c release-manifest.json.sha256)

source_sha="$(jq -r .source_sha "$manifest")"
backend_image="$(jq -r .backend_image "$manifest")"
edge_image="$(jq -r .edge_image "$manifest")"
target="$(jq -r .target "$manifest")"
change_id="$(jq -r .change_id "$manifest")"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]]
git cat-file -e "${source_sha}^{commit}"
git merge-base --is-ancestor "$source_sha" origin/main
[[ "$backend_image" =~ @sha256:[0-9a-f]{64}$ ]]
[[ "$edge_image" =~ @sha256:[0-9a-f]{64}$ ]]
[[ "$change_id" =~ ^[A-Za-z0-9._-]+$ ]]
case "$target" in staging-readonly|production-readonly) ;; *) exit 1 ;; esac
jq -e '.deployment_read_only == true and .live_trading_authorized == false and .real_money_authorized == false' \
  "$manifest" >/dev/null

printf 'source_sha=%s\n' "$source_sha" >>"$GITHUB_OUTPUT"
printf 'backend_image=%s\n' "$backend_image" >>"$GITHUB_OUTPUT"
printf 'edge_image=%s\n' "$edge_image" >>"$GITHUB_OUTPUT"
printf 'target=%s\n' "$target" >>"$GITHUB_OUTPUT"
printf 'change_id=%s\n' "$change_id" >>"$GITHUB_OUTPUT"
