#!/bin/bash
set -euo pipefail

base_url=${BEYVRA_STAGING_URL:-https://staging.beyvra.com}
statsd_host=${STATSD_HOST:-127.0.0.1}
statsd_port=${STATSD_PORT:-9125}
nginx_container=${NGINX_CONTAINER:-backend-nginx-1}
window=${NGINX_LOG_WINDOW:-2m}

emit() {
  local metric=$1 value=$2
  printf '%s:%s|g\n' "$metric" "$value" > "/dev/udp/${statsd_host}/${statsd_port}"
}

http_code() {
  curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
    --max-time 10 "$@"
}

providers=$(http_code "${base_url}/api/v1/auth/providers" || true)
invalid_login=$(http_code \
  --header 'Content-Type: application/json' \
  --data '{"email":"nonexistent-certification-user@invalid.example","password":"not-a-real-password"}' \
  "${base_url}/api/user/token/" || true)
ws_probe_key='Y2VydGlmaWNhdGlvbi10ZXN0' # gitleaks:allow fixed RFC 6455 probe value
websocket=$(http_code --http1.1 \
  --header 'Connection: Upgrade' \
  --header 'Upgrade: websocket' \
  --header 'Sec-WebSocket-Version: 13' \
  --header "Sec-WebSocket-Key: ${ws_probe_key}" \
  "${base_url}/ws/nonexistent-certification/" || true)
centrifugo=$(http_code "${base_url}/ws/v2/health" || true)

auth_ok=0
websocket_ok=0
centrifugo_ok=0
[[ "$providers" == 200 && "$invalid_login" == 401 ]] && auth_ok=1
case "$websocket" in 000|502|503|504) ;; *) websocket_ok=1 ;; esac
[[ "$centrifugo" == 200 ]] && centrifugo_ok=1

recent_logs=$(docker logs "$nginx_container" --since "$window" 2>&1 || true)
http_502=$(grep -Ec '" 502 [0-9]+' <<<"$recent_logs" || true)
connection_refused=$(grep -Fc 'connect() failed (111: Connection refused)' <<<"$recent_logs" || true)
dns_failures=$(grep -Eic 'host not found|could not be resolved|no resolver defined|service unavailable.*resolve' <<<"$recent_logs" || true)

probe_ok=0
if [[ "$auth_ok" == 1 && "$websocket_ok" == 1 && "$centrifugo_ok" == 1 ]]; then
  probe_ok=1
fi

emit codestra.staging.nginx_upstream_probe.ok "$probe_ok"
emit codestra.staging.auth_endpoint.available "$auth_ok"
emit codestra.staging.websocket_upstream.available "$websocket_ok"
emit codestra.staging.centrifugo.available "$centrifugo_ok"
emit codestra.staging.nginx.http_502_2m "$http_502"
emit codestra.staging.nginx.connection_refused_2m "$connection_refused"
emit codestra.staging.nginx.dns_failure_2m "$dns_failures"
emit codestra.staging.nginx_upstream_probe.timestamp "$(date +%s)"

printf 'PROVIDERS_HTTP=%s\n' "$providers"
printf 'INVALID_LOGIN_HTTP=%s\n' "$invalid_login"
printf 'WEBSOCKET_HANDSHAKE_HTTP=%s\n' "$websocket"
printf 'CENTRIFUGO_HEALTH_HTTP=%s\n' "$centrifugo"
printf 'NGINX_502_2M=%s\n' "$http_502"
printf 'UPSTREAM_CONNECTION_REFUSED_2M=%s\n' "$connection_refused"
printf 'UPSTREAM_DNS_FAILURE_2M=%s\n' "$dns_failures"
printf 'NGINX_UPSTREAM_PROBE=%s\n' "$([[ "$probe_ok" == 1 ]] && echo PASS || echo FAIL)"

[[ "$probe_ok" == 1 ]]
