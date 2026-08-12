#!/bin/sh
set -eu

SERVER="${NATS_URL:-nats://nats:4222}"
TLS_ARGS=""
[ -n "${NATS_TLS_CA_FILE:-}" ] && TLS_ARGS="--tlsca $NATS_TLS_CA_FILE"
create() {
  name="$1"; shift
  nats --server "$SERVER" $TLS_ARGS stream add "$name" "$@" --storage file --retention limits \
    --max-age 24h --max-bytes 100000000 --max-msg-size 1048576 \
    --dupe-window 2m --max-msgs 1000000 --defaults >/dev/null 2>&1 || \
    nats --server "$SERVER" $TLS_ARGS stream info "$name" >/dev/null
}

create MARKET_TICKS --subjects 'market.tick.*'
create MARKET_QUOTES --subjects 'market.quote.*'
create MARKET_CANDLES --subjects 'market.candle.*.*'
create MARKET_ORDERBOOK --subjects 'market.orderbook.*'
create MARKET_TRADES --subjects 'market.trade.*'
create NEWS_EVENTS --subjects 'news.article.*' --subjects 'news.alert.*' --subjects 'news.economic.*'
create PRIVATE_ACCOUNT_EVENTS --subjects 'private.trade.*' --subjects 'private.order.*' --subjects 'private.portfolio.*' --subjects 'private.wallet.*' --subjects 'private.notification.*'
create SYSTEM_EVENTS --subjects 'system.status.*'
# Canonical application outbox subjects are retained independently from the
# realtime bridge. Domain consumers must use their own durable/inbox contract.
create APPLICATION_EVENTS --subjects 'application.>'

nats --server "$SERVER" $TLS_ARGS server check jetstream
