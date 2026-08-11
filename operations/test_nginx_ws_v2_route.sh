#!/bin/sh
set -eu

config=${1:-nginx/nginx.prod.conf.template}
expected='proxy_pass http://centrifugo/connection/websocket;'

if ! grep -Fq "$expected" "$config"; then
    printf 'WS_V2_ROUTE=FAIL expected=%s config=%s\n' "$expected" "$config" >&2
    exit 1
fi

if grep -Fq 'proxy_pass http://centrifugo/;' "$config"; then
    printf 'WS_V2_ROUTE=FAIL legacy_root_proxy_present config=%s\n' "$config" >&2
    exit 1
fi

printf 'WS_V2_ROUTE=PASS config=%s\n' "$config"
