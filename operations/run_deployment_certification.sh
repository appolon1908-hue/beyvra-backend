#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

required=(DEPLOY_RUN_ID DEPLOY_HOST DEPLOY_USER DEPLOY_SSH_KEY DEPLOY_KNOWN_HOSTS DEPLOY_PATH PUBLIC_SERVER_NAME VERIFICATION_BASE_URL CERTIFICATION_TOKEN_FILE CANARY_TRAFFIC_PERCENT EXTERNAL_CANARY_ROUTING_VERIFIED SOURCE_SHA BACKEND_IMAGE EDGE_IMAGE DEPLOYMENT_TARGET CHANGE_ID GITHUB_REPOSITORY)
for name in "${required[@]}"; do [[ -n "${!name:-}" ]] || { echo "Missing protected value: $name" >&2; exit 1; }; done
[[ "$DEPLOY_PATH" =~ ^/[A-Za-z0-9._/-]+$ ]]
[[ "$PUBLIC_SERVER_NAME" =~ ^[A-Za-z0-9.-]+$ ]]
[[ "$VERIFICATION_BASE_URL" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]
[[ "$CERTIFICATION_TOKEN_FILE" =~ ^/[A-Za-z0-9._/-]+$ ]]
[[ "$BACKEND_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]
[[ "$EDGE_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]
[[ "$CANARY_TRAFFIC_PERCENT" =~ ^[0-9]+$ ]]
case "$EXTERNAL_CANARY_ROUTING_VERIFIED" in true|false) ;; *) exit 1 ;; esac

cleanup() { rm -rf ~/.ssh certification.env certification-bundle.tgz; }
trap cleanup EXIT
mkdir -p /tmp/beyvra-deployment evidence
gh run download "$DEPLOY_RUN_ID" --repo "$GITHUB_REPOSITORY" \
  --name "beyvra-backend-deployment-${DEPLOYMENT_TARGET}-${CHANGE_ID}" \
  --dir /tmp/beyvra-deployment
find /tmp/beyvra-deployment -type f -name candidate.env -print -quit | grep -q .
find /tmp/beyvra-deployment -type f -name candidate-public-evidence.json -print -quit | grep -q .

tar -czf certification-bundle.tgz \
  operations/certify_remote_readonly.sh \
  operations/release_cert_runtime.sh \
  operations/release_cert_state.sh \
  operations/rehearse_readonly_rollback.sh \
  operations/verify_release_identity.py \
  operations/verify_previous_release.py \
  operations/verify_metrics_zero.py \
  operations/verify_edge_policy.py \
  scripts/certify_staging_api.py \
  scripts/database_fingerprint.py
! tar -tzf certification-bundle.tgz | grep -E '(^/|(^|/)\.\.(/|$))' >/dev/null

{
  printf 'SOURCE_SHA=%q\n' "$SOURCE_SHA"
  printf 'BACKEND_IMAGE=%q\n' "$BACKEND_IMAGE"
  printf 'EDGE_IMAGE=%q\n' "$EDGE_IMAGE"
  printf 'CHANGE_ID=%q\n' "$CHANGE_ID"
  printf 'DEPLOYMENT_TARGET=%q\n' "$DEPLOYMENT_TARGET"
  printf 'PUBLIC_BASE_URL=%q\n' "https://${PUBLIC_SERVER_NAME}"
  printf 'VERIFICATION_BASE_URL=%q\n' "$VERIFICATION_BASE_URL"
  printf 'CERTIFICATION_TOKEN_FILE=%q\n' "$CERTIFICATION_TOKEN_FILE"
  printf 'CANARY_TRAFFIC_PERCENT=%q\n' "$CANARY_TRAFFIC_PERCENT"
  printf 'EXTERNAL_CANARY_ROUTING_VERIFIED=%q\n' "$EXTERNAL_CANARY_ROUTING_VERIFIED"
} > certification.env
chmod 600 certification.env

install -d -m 700 ~/.ssh
printf '%s\n' "$DEPLOY_SSH_KEY" > ~/.ssh/id_ed25519
chmod 600 ~/.ssh/id_ed25519
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > ~/.ssh/known_hosts
chmod 600 ~/.ssh/known_hosts
remote="${DEPLOY_USER}@${DEPLOY_HOST}"
incoming="/tmp/beyvra-cert-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
scp certification-bundle.tgz "${remote}:${incoming}.tgz"
scp certification.env "${remote}:${incoming}.env"
ssh "$remote" "bash -se" <<REMOTE
set -euo pipefail
cd '$DEPLOY_PATH'
tar -xzf '${incoming}.tgz' -C '$DEPLOY_PATH'
install -m 600 '${incoming}.env' '$DEPLOY_PATH/releases/$CHANGE_ID/certification.env'
rm -f '${incoming}.tgz' '${incoming}.env'
set -a
. 'releases/$CHANGE_ID/workflow.env'
. 'releases/$CHANGE_ID/certification.env'
set +a
trap 'rm -f "releases/$CHANGE_ID/certification.env"' EXIT
./operations/certify_remote_readonly.sh
REMOTE

scp -r "${remote}:${DEPLOY_PATH}/releases/${CHANGE_ID}/." evidence/
rm -f evidence/workflow.env evidence/certification.env evidence/*/workflow.env evidence/*/certification.env
