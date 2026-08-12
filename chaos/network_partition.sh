#!/bin/sh
set -eu
# Disconnects two services only on the internal chaos network and always reconnects.
COMPOSE_FILE=${COMPOSE_FILE:-chaos/docker-compose.yml}
NETWORK=${CHAOS_NETWORK:-beyvara-chaos_chaos}
left=${1:?left service}; right=${2:?right service}; shift 2
case "$left:$right" in
  runner:nats|runner:redis|runner:postgres|runner:centrifugo) ;;
  *) echo "partition pair refused" >&2; exit 2 ;;
esac
container=$(docker compose -f "$COMPOSE_FILE" ps -q "$right")
cleanup() { docker network connect "$NETWORK" "$container" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
docker network disconnect "$NETWORK" "$container"
"$@"
cleanup
trap - EXIT INT TERM
remaining=$(docker network inspect "$NETWORK" --format '{{len .Containers}}')
test "$remaining" -ge 1
echo NETWORK_CLEANUP=PASS
echo NETWORK_RULES_REMAINING=0
