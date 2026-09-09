#!/usr/bin/env bash
# Runtime inspection helpers for Beyvra read-only certification.

cert_release_dir="releases/${CHANGE_ID}"
cert_compose=(docker compose --project-directory . -f docker-compose.production.yaml)
cert_compose_all=("${cert_compose[@]}" --profile release --profile background --profile simulation)
cert_image_variables=(BACKEND_IMAGE EDGE_IMAGE POSTGRES_IMAGE REDIS_IMAGE NATS_IMAGE CENTRIFUGO_IMAGE STATSD_EXPORTER_IMAGE)
cert_active_services=(web daphne realtime_bridge nginx db-backup statsd-exporter postgres redis nats centrifugo)
cert_disabled_services=(canonical-outbox-publisher celery_worker celery_beat celery-flower chart-data-publisher demo-event-publisher simulated-execution-consumer)

cert_service_variable() {
  case "$1" in
    web|daphne|realtime_bridge) printf BACKEND_IMAGE ;;
    nginx) printf EDGE_IMAGE ;;
    db-backup|postgres) printf POSTGRES_IMAGE ;;
    redis) printf REDIS_IMAGE ;;
    nats) printf NATS_IMAGE ;;
    centrifugo) printf CENTRIFUGO_IMAGE ;;
    statsd-exporter) printf STATSD_EXPORTER_IMAGE ;;
    *) return 1 ;;
  esac
}

cert_verify_running_tuple() {
  local service variable container observed
  for service in "${cert_active_services[@]}"; do
    container="$("${cert_compose_all[@]}" ps -q "$service")"
    [[ -n "$container" ]] || { echo "Required service is not running: $service" >&2; return 1; }
    variable="$(cert_service_variable "$service")"
    observed="$(docker inspect --format '{{.Config.Image}}' "$container")"
    [[ "$observed" == "${!variable}" ]] || { echo "Runtime digest mismatch for $service." >&2; return 1; }
  done
  for service in "${cert_disabled_services[@]}"; do
    if [[ -n "$("${cert_compose_all[@]}" ps -q "$service" 2>/dev/null || true)" ]]; then
      echo "Effectful/background service is running: $service" >&2
      return 1
    fi
  done
}

cert_local_edge_url() {
  local address
  address="$("${cert_compose[@]}" port nginx 8080 | head -n 1)"
  [[ -n "$address" ]]
  case "$address" in
    0.0.0.0:*) address="127.0.0.1:${address##*:}" ;;
    "[::]:"*) address="127.0.0.1:${address##*:}" ;;
  esac
  printf 'http://%s\n' "$address"
}

cert_capture_web_url() {
  local path=$1 output=$2 web
  web="$("${cert_compose_all[@]}" ps -q web)"
  docker exec "$web" python - "$path" >"$output" <<'PY'
import sys
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:8000" + sys.argv[1], timeout=30) as response:
    if response.status != 200:
        raise SystemExit(f"unexpected HTTP status {response.status}")
    sys.stdout.buffer.write(response.read(16 * 1024 * 1024))
PY
  test -s "$output"
}

cert_capture_statsd_metrics() {
  local output=$1 web
  web="$("${cert_compose_all[@]}" ps -q web)"
  docker exec "$web" python - >"$output" <<'PY'
import sys
import urllib.request
with urllib.request.urlopen("http://statsd-exporter:9102/metrics", timeout=30) as response:
    if response.status != 200:
        raise SystemExit(f"unexpected HTTP status {response.status}")
    sys.stdout.buffer.write(response.read(16 * 1024 * 1024))
PY
  grep -Eq '^(statsd_exporter_build_info|go_build_info)' "$output"
}

cert_capture_database_fingerprint() {
  local output=$1 web
  web="$("${cert_compose_all[@]}" ps -q web)"
  docker exec -e FINGERPRINT_STATEMENT_TIMEOUT_MS=1800000 "$web" \
    python /scripts/database_fingerprint.py >"$output"
  python - "$output" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
assert payload["table_count"] > 0
assert len(payload["database_fingerprint"]) == 64
PY
}
