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

create MARKET_EVENTS --subjects 'market.>'
create NEWS_EVENTS --subjects 'news.>'
create PRIVATE_ACCOUNT_EVENTS --subjects 'private.>'
create SYSTEM_EVENTS --subjects 'system.>'
create TRADING_EVENTS --subjects 'trading.>'
create POST_TRADE_EVENTS --subjects 'post_trade.>'
create VALUATION_EVENTS --subjects 'valuation.>'
create TREASURY_EVENTS --subjects 'treasury.>'
create REGULATORY_EVENTS --subjects 'regulatory.>'
create COMPLIANCE_EVENTS --subjects 'compliance.>'

nats --server "$SERVER" $TLS_ARGS server check jetstream
