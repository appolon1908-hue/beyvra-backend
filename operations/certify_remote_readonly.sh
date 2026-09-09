#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

required=(SOURCE_SHA BACKEND_IMAGE EDGE_IMAGE CHANGE_ID DEPLOYMENT_TARGET PUBLIC_BASE_URL VERIFICATION_BASE_URL CERTIFICATION_TOKEN_FILE CANARY_TRAFFIC_PERCENT EXTERNAL_CANARY_ROUTING_VERIFIED)
for name in "${required[@]}"; do [[ -n "${!name:-}" ]] || { echo "Missing certification variable: $name" >&2; exit 1; }; done
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
for name in BACKEND_IMAGE EDGE_IMAGE; do [[ "${!name}" =~ @sha256:[0-9a-f]{64}$ ]]; done
[[ "$CHANGE_ID" =~ ^[A-Za-z0-9._-]+$ ]]
for name in PUBLIC_BASE_URL VERIFICATION_BASE_URL; do [[ "${!name}" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]; done
[[ "$CANARY_TRAFFIC_PERCENT" =~ ^[0-9]+$ ]] && (( CANARY_TRAFFIC_PERCENT <= 100 ))
case "$EXTERNAL_CANARY_ROUTING_VERIFIED" in true|false) ;; *) exit 1 ;; esac
case "$DEPLOYMENT_TARGET" in
  staging-readonly) APP_DEPLOYMENT_ENV=staging ;;
  production-readonly)
    APP_DEPLOYMENT_ENV=production
    (( CANARY_TRAFFIC_PERCENT <= 1 ))
    [[ "$EXTERNAL_CANARY_ROUTING_VERIFIED" == true ]]
    ;;
  *) exit 1 ;;
esac
export APP_DEPLOYMENT_ENV
[[ "$CERTIFICATION_TOKEN_FILE" =~ ^/[A-Za-z0-9._/-]+$ ]]
[[ "$CERTIFICATION_TOKEN_FILE" != *"/../"* && "$CERTIFICATION_TOKEN_FILE" != *"/.." ]]
[[ -f "$CERTIFICATION_TOKEN_FILE" && -r "$CERTIFICATION_TOKEN_FILE" ]]
! find "$CERTIFICATION_TOKEN_FILE" -perm /077 -print -quit | grep -q .

release_dir="releases/${CHANGE_ID}"
files=(docker-compose.production.yaml operations/release_cert_runtime.sh operations/release_cert_state.sh operations/rehearse_readonly_rollback.sh operations/verify_release_identity.py operations/verify_previous_release.py operations/verify_metrics_zero.py operations/verify_edge_policy.py scripts/certify_staging_api.py scripts/database_fingerprint.py "$release_dir/workflow.env" "$release_dir/candidate.env" "$release_dir/previous.env" "$release_dir/backup-evidence.txt" "$release_dir/migration-evidence.txt")
for path in "${files[@]}"; do [[ -f "$path" ]] || { echo "Required certification evidence is missing: $path" >&2; exit 1; }; done
source operations/release_cert_runtime.sh
source operations/release_cert_state.sh

docker compose version >/dev/null
docker info >/dev/null
recorded="$(sed -n 's/^SOURCE_SHA=//p' "$release_dir/candidate.env" | tr -d "'\\")"
[[ "$recorded" == "$SOURCE_SHA" ]]
cert_verify_running_tuple
cert_verify_backup_evidence

metrics_before="$release_dir/metrics-before.prom"
metrics_after="$release_dir/metrics-after.prom"
cert_capture_web_url /metrics "$metrics_before"
cert_capture_statsd_metrics "$release_dir/statsd-exporter.prom"
python3 operations/verify_release_identity.py --base-url "$VERIFICATION_BASE_URL" \
  --source-sha "$SOURCE_SHA" --image-digest "$BACKEND_IMAGE" \
  --output "$release_dir/certification-identity.json"
python3 operations/verify_edge_policy.py --base-url "$VERIFICATION_BASE_URL" \
  --source-sha "$SOURCE_SHA" --image-digest "$BACKEND_IMAGE" \
  --output "$release_dir/certification-edge-policy.json"

token="$(tr -d '\r\n' <"$CERTIFICATION_TOKEN_FILE")"
[[ -n "$token" && ${#token} -le 16384 ]]
BEYVRA_STAGING_ACCESS_TOKEN="$token" ALLOW_NON_STAGING_CERTIFICATION=yes \
  python3 scripts/certify_staging_api.py --base-url "$VERIFICATION_BASE_URL" \
  --output "$release_dir/certification-api.json"
unset token
cert_capture_web_url /metrics "$metrics_after"
python3 operations/verify_metrics_zero.py --before "$metrics_before" --after "$metrics_after" \
  --output "$release_dir/certification-zero-effects.json"

if [[ "$DEPLOYMENT_TARGET" == staging-readonly ]]; then
  operations/rehearse_readonly_rollback.sh
fi

cat >"$release_dir/certification-summary.json" <<EOF_SUMMARY
{
  "schema_version": 1,
  "source_sha": "${SOURCE_SHA}",
  "backend_image": "${BACKEND_IMAGE}",
  "edge_image": "${EDGE_IMAGE}",
  "target": "${DEPLOYMENT_TARGET}",
  "public_base_url": "${PUBLIC_BASE_URL}",
  "verification_base_url": "${VERIFICATION_BASE_URL}",
  "canary_traffic_percent": ${CANARY_TRAFFIC_PERCENT},
  "external_canary_routing_verified": ${EXTERNAL_CANARY_ROUTING_VERIFIED},
  "live_effects": 0,
  "overall": "PASS"
}
EOF_SUMMARY
printf 'CERTIFICATION_RESULT=PASS\n'
