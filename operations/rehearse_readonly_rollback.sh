#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

source operations/release_cert_runtime.sh
source operations/release_cert_state.sh
for path in "${cert_release_dir}/previous.env" "${cert_release_dir}/static-before.tgz"; do
  [[ -f "$path" ]] || { echo "Required rollback evidence is missing: $path" >&2; exit 1; }
done

candidate_runtime="${cert_release_dir}/candidate-runtime.env"
fingerprint_before="${cert_release_dir}/database-fingerprint-before.json"
fingerprint_after="${cert_release_dir}/database-fingerprint-after.json"
cert_save_runtime "$candidate_runtime"
cert_capture_database_fingerprint "$fingerprint_before"

cert_export_runtime "${cert_release_dir}/previous.env"
for variable in "${cert_image_variables[@]}"; do
  [[ "${!variable}" =~ @sha256:[0-9a-f]{64}$ ]] || { echo "Previous $variable is not immutable." >&2; exit 1; }
done
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "Previous source identity is incomplete." >&2; exit 1; }
previous_source=$SOURCE_SHA
previous_backend=$BACKEND_IMAGE

rollback_started_ms="$(date +%s%3N)"
cert_restore_static_snapshot
cert_start_runtime
previous_local_url="$(cert_local_edge_url)"
python3 operations/verify_previous_release.py \
  --base-url "$previous_local_url" --source-sha "$previous_source" \
  --image-digest "$previous_backend" \
  --output "${cert_release_dir}/rollback-previous-evidence.json"
rollback_ready_ms="$(date +%s%3N)"

cert_export_runtime "$candidate_runtime"
candidate_source=$SOURCE_SHA
candidate_backend=$BACKEND_IMAGE
restore_started_ms="$(date +%s%3N)"
cert_start_candidate_release
cert_verify_running_tuple
candidate_local_url="$(cert_local_edge_url)"
python3 operations/verify_release_identity.py \
  --base-url "$candidate_local_url" --source-sha "$candidate_source" \
  --image-digest "$candidate_backend" \
  --output "${cert_release_dir}/rollback-candidate-restored-evidence.json"
python3 operations/verify_edge_policy.py \
  --base-url "$candidate_local_url" --source-sha "$candidate_source" \
  --image-digest "$candidate_backend" \
  --output "${cert_release_dir}/rollback-candidate-edge-policy.json"
restore_ready_ms="$(date +%s%3N)"

cert_capture_database_fingerprint "$fingerprint_after"
python3 - "$fingerprint_before" "$fingerprint_after" \
  "${cert_release_dir}/rollback-rehearsal.json" \
  "$rollback_started_ms" "$rollback_ready_ms" "$restore_started_ms" "$restore_ready_ms" <<'PY'
import json
import sys
from pathlib import Path
before = json.loads(Path(sys.argv[1]).read_text())
after = json.loads(Path(sys.argv[2]).read_text())
integrity = before["database_fingerprint"] == after["database_fingerprint"]
evidence = {
    "schema_version": 1,
    "rollback_rto_seconds": round((int(sys.argv[5]) - int(sys.argv[4])) / 1000, 3),
    "candidate_restore_rto_seconds": round((int(sys.argv[7]) - int(sys.argv[6])) / 1000, 3),
    "rpo_seconds": 0 if integrity else None,
    "data_integrity": "PASS" if integrity else "FAIL",
    "overall": "PASS" if integrity else "FAIL",
}
Path(sys.argv[3]).write_text(json.dumps(evidence, indent=2) + "\n")
if not integrity:
    raise SystemExit(1)
PY

before="${cert_release_dir}/restored-metrics-before.prom"
after="${cert_release_dir}/restored-metrics-after.prom"
cert_capture_web_url /metrics "$before"
python3 operations/verify_release_identity.py \
  --base-url "$VERIFICATION_BASE_URL" --source-sha "$candidate_source" \
  --image-digest "$candidate_backend" \
  --output "${cert_release_dir}/rollback-candidate-public-evidence.json"
cert_capture_web_url /metrics "$after"
python3 operations/verify_metrics_zero.py --before "$before" --after "$after" \
  --output "${cert_release_dir}/rollback-zero-effects.json"
