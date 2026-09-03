#!/usr/bin/env bash
set -euo pipefail

script=${1:-operations/check_nginx_upstreams.sh}

bash -n "$script"

key=$(sed -n "s/^ws_probe_key='\([^']*\)'.*/\1/p" "$script")
[[ -n "$key" ]]
[[ $(printf '%s' "$key" | base64 --decode | wc -c) -eq 16 ]]

grep -Fq '"${base_url}/ws/v2/"' "$script"
grep -Fq '[[ "$centrifugo" == 101 ]]' "$script"
if grep -Fq '/ws/v2/health' "$script"; then
  echo 'probe must target the real WebSocket route, not a nonexistent health path' >&2
  exit 1
fi
