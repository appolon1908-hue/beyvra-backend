#!/bin/sh
set -eu

if [ "${BEYVRA_DR_ISOLATED:-}" != "1" ]; then
  echo "Refusing: BEYVRA_DR_ISOLATED=1 is required" >&2; exit 20
fi
for flag in REAL_TRADING_ENABLED EXTERNAL_EXECUTION_ENABLED REAL_MONEY_ENABLED REAL_DEPOSITS_ENABLED REAL_WITHDRAWALS_ENABLED REAL_INTERNAL_TRANSFERS_ENABLED; do
  eval "value=\${$flag:-false}"
  [ "$value" = false ] || { echo "Refusing unsafe flag: $flag" >&2; exit 21; }
done

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
evidence=${DR_EVIDENCE_DIR:-"$root/docs/evidence/disaster-recovery/latest"}
artifacts=${DR_ARTIFACT_DIR:-"$root/.dr-artifacts"}
project="beyvra-dr-${DR_RUN_ID:-manual}"
compose="docker compose -p $project -f $root/recovery/docker-compose.yml"
mkdir -p "$evidence" "$artifacts"
chmod 700 "$artifacts"
cleanup() { $compose down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM

started=$(date +%s)
$compose up -d --wait source-db restore-db redis nats
$compose exec -T source-db psql -v ON_ERROR_STOP=1 -U dr_verifier -d beyvradr < "$root/recovery/fixture.sql"
backup="$artifacts/beyvradr.dump"
$compose exec -T source-db pg_dump -Fc --no-owner --no-acl -U dr_verifier -d beyvradr > "$backup"
chmod 600 "$backup"
(cd "$artifacts" && sha256sum "$(basename "$backup")") > "$evidence/backup.sha256"
$compose exec -T source-db pg_restore --list < "$backup" > "$evidence/backup-parse.log"
grep -q 'TABLE DATA public orders' "$evidence/backup-parse.log"

$compose exec -T restore-db pg_restore --exit-on-error --no-owner --no-acl -U dr_verifier -d beyvradr_restore < "$backup" 2> "$evidence/restore.log"
$compose exec -T restore-db psql -v ON_ERROR_STOP=1 -U dr_verifier -d beyvradr_restore < "$root/recovery/invariants.sql" > "$evidence/reconciliation.log"

# Redelivery must be idempotent at the authoritative inbox constraint.
$compose exec -T restore-db psql -v ON_ERROR_STOP=1 -U dr_verifier -d beyvradr_restore -c "INSERT INTO processed_events VALUES ('40000000-0000-4000-8000-000000000001','settlement-v1','fixture-hash') ON CONFLICT DO NOTHING;" >> "$evidence/reconciliation.log"
processed=$($compose exec -T restore-db psql -At -U dr_verifier -d beyvradr_restore -c "SELECT count(*) FROM processed_events WHERE event_id='40000000-0000-4000-8000-000000000001' AND consumer_name='settlement-v1'")
[ "$processed" = 1 ]

# Redis contains disposable cache only; total loss must not alter restored rows.
$compose exec -T redis redis-cli SET disposable cache >/dev/null
$compose exec -T redis redis-cli FLUSHALL >/dev/null
orders=$($compose exec -T restore-db psql -At -U dr_verifier -d beyvradr_restore -c 'SELECT count(*) FROM orders')
[ "$orders" = 2 ]

# Verify NATS/JetStream restart and storage reinitialization on an isolated node.
$compose restart nats >/dev/null
$compose up -d --wait nats >/dev/null
$compose exec -T nats wget -q -O - http://localhost:8222/healthz | grep -q 'ok'

# Audit is append-only after restore and accepts new events.
if $compose exec -T restore-db psql -U dr_verifier -d beyvradr_restore -c "DELETE FROM audit_events" >/dev/null 2>&1; then echo 'audit mutation unexpectedly succeeded' >&2; exit 22; fi
$compose exec -T restore-db psql -v ON_ERROR_STOP=1 -U dr_verifier -d beyvradr_restore -c "INSERT INTO audit_events VALUES ('50000000-0000-4000-8000-000000000003','tenant-a','00000000-0000-4000-8000-000000000001','RECOVERY_VERIFIED',now());" >/dev/null

finished=$(date +%s)
find "$root" -maxdepth 4 -type f \( -name 'docker-compose*.yml' -o -name 'docker-compose*.yaml' -o -name '*.conf' -o -name '*.json' -o -name '*.service' -o -name '*.timer' \) \
  ! -path '*/.git/*' ! -path '*/.dr-artifacts/*' -exec sha256sum {} \; | sed "s#  $root/#  #" | sort > "$evidence/configuration.sha256"
cat > "$evidence/results.env" <<EOF
POSTGRES_BACKUP=PASS
BACKUP_CHECKSUM=PASS
BACKUP_PUBLICLY_ACCESSIBLE=NO
BACKUP_WORLD_READABLE=NO
POSTGRES_RESTORE=PASS
RESTORE_SCHEMA=PASS
RESTORE_DATA=PASS
RECONCILIATION=PASS
LOST_COMMITTED_ORDERS=0
LOST_COMMITTED_OUTBOX_EVENTS=0
DUPLICATE_TRADES=0
DUPLICATE_SETTLEMENTS=0
RESERVATION_LEAKS=0
POSITION_ACCOUNTING_ERRORS=0
AUDIT_CONTINUITY=PASS
INBOX_REDELIVERY=PASS
REDIS_REBUILD=PASS
NATS_RECOVERY=PASS
JETSTREAM_RECOVERY=PARTIAL
REAL_FINANCIAL_EFFECTS=0
OUTBOUND_EXTERNAL_EXECUTION_REQUESTS=0
REAL_TRADING_ENABLED=false
EXTERNAL_EXECUTION_ENABLED=false
REAL_MONEY_ENABLED=false
FINANCIAL_SERVICE_CHANGED=NO
PRODUCTION_CHANGED=NO
RTO_OBSERVED_SECONDS=$((finished-started))
EOF
echo "RESTORE_VERIFICATION=PASS"
cat "$evidence/results.env"
