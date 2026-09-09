#!/usr/bin/env bash
set -Eeuo pipefail

required=(
  BACKEND_IMAGE
  EDGE_IMAGE
  POSTGRES_IMAGE
  REDIS_IMAGE
  NATS_IMAGE
  CENTRIFUGO_IMAGE
  STATSD_EXPORTER_IMAGE
  SOURCE_SHA
  CHANGE_ID
  DEPLOYMENT_TARGET
  PUBLIC_SERVER_NAME
  PUBLIC_BASE_URL
  FINANCIAL_API_NETWORK
  MONITORING_NETWORK
  BACKUP_OFFHOST_PATH
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf 'Missing required variable: %s\n' "$name" >&2
    exit 1
  fi
done

digest_pattern='@sha256:[0-9a-f]{64}$'
image_variables=(
  BACKEND_IMAGE
  EDGE_IMAGE
  POSTGRES_IMAGE
  REDIS_IMAGE
  NATS_IMAGE
  CENTRIFUGO_IMAGE
  STATSD_EXPORTER_IMAGE
)
for name in "${image_variables[@]}"; do
  if [[ ! "${!name}" =~ $digest_pattern ]]; then
    printf '%s must be an immutable repository@sha256 digest\n' "$name" >&2
    exit 1
  fi
done

if [[ ! "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "SOURCE_SHA must be a full lower-case Git SHA." >&2
  exit 1
fi
if [[ ! "$CHANGE_ID" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "CHANGE_ID contains unsupported characters." >&2
  exit 1
fi
if [[ ! "$PUBLIC_SERVER_NAME" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "PUBLIC_SERVER_NAME is not a valid DNS name." >&2
  exit 1
fi
if [[ "$PUBLIC_BASE_URL" != "https://${PUBLIC_SERVER_NAME}" ]]; then
  echo "PUBLIC_BASE_URL must be the HTTPS URL for PUBLIC_SERVER_NAME." >&2
  exit 1
fi
for name in FINANCIAL_API_NETWORK MONITORING_NETWORK; do
  if [[ ! "${!name}" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    printf '%s contains unsupported characters.\n' "$name" >&2
    exit 1
  fi
done
if [[ ! "$BACKUP_OFFHOST_PATH" =~ ^/[A-Za-z0-9._/-]+$ ]] \
  || [[ "$BACKUP_OFFHOST_PATH" == *"/../"* ]] \
  || [[ "$BACKUP_OFFHOST_PATH" == *"/.." ]]; then
  echo "BACKUP_OFFHOST_PATH must be a safe absolute path." >&2
  exit 1
fi
if [[ ! -d "$BACKUP_OFFHOST_PATH" ]]; then
  echo "BACKUP_OFFHOST_PATH must already exist as a mounted directory." >&2
  exit 1
fi

case "$DEPLOYMENT_TARGET" in
  staging-readonly)
    APP_DEPLOYMENT_ENV=staging
    ;;
  production-readonly)
    APP_DEPLOYMENT_ENV=production
    if ! command -v findmnt >/dev/null 2>&1; then
      echo "findmnt is required to prove the production off-host mount." >&2
      exit 1
    fi
    offhost_source="$(findmnt -n -o SOURCE -T "$BACKUP_OFFHOST_PATH")"
    root_source="$(findmnt -n -o SOURCE -T /)"
    if [[ -z "$offhost_source" || "$offhost_source" == "$root_source" ]]; then
      echo "Production backup path is not proven off-host." >&2
      exit 1
    fi
    ;;
  *)
    echo "DEPLOYMENT_TARGET must be staging-readonly or production-readonly." >&2
    exit 1
    ;;
esac

ALLOW_SCHEMA_MIGRATIONS="${ALLOW_SCHEMA_MIGRATIONS:-false}"
MIGRATION_COMPATIBILITY_APPROVED="${MIGRATION_COMPATIBILITY_APPROVED:-false}"
case "$ALLOW_SCHEMA_MIGRATIONS" in
  true|false) ;;
  *)
    echo "ALLOW_SCHEMA_MIGRATIONS must be true or false." >&2
    exit 1
    ;;
esac
case "$MIGRATION_COMPATIBILITY_APPROVED" in
  true|false) ;;
  *)
    echo "MIGRATION_COMPATIBILITY_APPROVED must be true or false." >&2
    exit 1
    ;;
esac
if [[ "$ALLOW_SCHEMA_MIGRATIONS" == "true" \
      && "$MIGRATION_COMPATIBILITY_APPROVED" != "true" ]]; then
  echo "Schema changes require MIGRATION_COMPATIBILITY_APPROVED=true." >&2
  exit 1
fi

for command in docker python3; do
  command -v "$command" >/dev/null 2>&1
done
docker compose version >/dev/null
docker info >/dev/null

required_files=(
  .env
  docker-compose.production.yaml
  operations/verify_release_identity.py
  scripts/backup-loop.sh
  scripts/backup-once.sh
  infra/realtime-v2/nats.conf
  infra/realtime-v2/centrifugo.json
  infra/realtime-v2/tls/ca.crt
  infra/realtime-v2/tls/centrifugo-client.crt
  infra/realtime-v2/tls/centrifugo-client.key
  infra/realtime-v2/tls/bridge-client.crt
  infra/realtime-v2/tls/bridge-client.key
  statsd-exporter/statsd.conf
)
for path in "${required_files[@]}"; do
  if [[ ! -f "$path" ]]; then
    printf 'Required deployment file is missing: %s\n' "$path" >&2
    exit 1
  fi
done
for path in media secrets secrets/financial; do
  if [[ ! -d "$path" ]]; then
    printf 'Required deployment directory is missing: %s\n' "$path" >&2
    exit 1
  fi
done
docker network inspect "$FINANCIAL_API_NETWORK" >/dev/null
docker network inspect "$MONITORING_NETWORK" >/dev/null

compose=(
  docker compose
  --project-directory .
  -f docker-compose.production.yaml
)
compose_all=(
  "${compose[@]}"
  --profile release
  --profile background
  --profile simulation
)
release_dir="releases/${CHANGE_ID}"
mkdir -p "$release_dir"
chmod 700 "$release_dir"

export \
  APP_DEPLOYMENT_ENV \
  BACKEND_IMAGE EDGE_IMAGE POSTGRES_IMAGE REDIS_IMAGE NATS_IMAGE \
  CENTRIFUGO_IMAGE STATSD_EXPORTER_IMAGE SOURCE_SHA CHANGE_ID \
  PUBLIC_SERVER_NAME FINANCIAL_API_NETWORK MONITORING_NETWORK \
  BACKUP_OFFHOST_PATH ALLOW_SCHEMA_MIGRATIONS

configured_images="$("${compose_all[@]}" config --images | sed '/^$/d' | sort -u)"
if [[ -z "$configured_images" ]] \
  || grep -Ev '@sha256:[0-9a-f]{64}$' <<<"$configured_images" >/dev/null; then
  echo "Every production image must resolve to an immutable digest:" >&2
  printf '%s\n' "$configured_images" >&2
  exit 1
fi
printf '%s\n' "$configured_images" > "${release_dir}/configured-images.txt"

declare -A service_for_variable=(
  [BACKEND_IMAGE]=web
  [EDGE_IMAGE]=nginx
  [POSTGRES_IMAGE]=postgres
  [REDIS_IMAGE]=redis
  [NATS_IMAGE]=nats
  [CENTRIFUGO_IMAGE]=centrifugo
  [STATSD_EXPORTER_IMAGE]=statsd-exporter
)
declare -A previous_images=()
previous_source=""
previous_complete=true

for variable in "${image_variables[@]}"; do
  service="${service_for_variable[$variable]}"
  container="$("${compose_all[@]}" ps -q "$service" 2>/dev/null || true)"
  observed=""
  if [[ -n "$container" ]]; then
    observed="$(docker inspect --format '{{.Config.Image}}' "$container")"
    if [[ ! "$observed" =~ $digest_pattern ]]; then
      resolved="$(
        docker image inspect \
          --format '{{range .RepoDigests}}{{println .}}{{end}}' \
          "$observed" 2>/dev/null | head -n 1 || true
      )"
      if [[ "$resolved" =~ $digest_pattern ]]; then
        observed="$resolved"
      fi
    fi
  fi
  previous_images["$variable"]="$observed"
  if [[ ! "$observed" =~ $digest_pattern ]]; then
    previous_complete=false
  fi
done

if [[ -n "${previous_images[BACKEND_IMAGE]}" ]]; then
  previous_source="$(
    docker image inspect \
      --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
      "${previous_images[BACKEND_IMAGE]}" 2>/dev/null || true
  )"
fi

{
  printf 'SOURCE_SHA=%q\n' "$previous_source"
  for variable in "${image_variables[@]}"; do
    printf '%s=%q\n' "$variable" "${previous_images[$variable]}"
  done
} > "${release_dir}/previous.env"

if [[ "$DEPLOYMENT_TARGET" == "production-readonly" \
      && "$previous_complete" != "true" ]]; then
  echo "Production requires a complete immutable previous candidate." >&2
  exit 1
fi

while IFS= read -r image; do
  docker pull "$image"
  docker image inspect "$image" >/dev/null
done <<<"$configured_images"

candidate_started=false
static_snapshot_created=false
rollback_started=false

local_edge_url() {
  local address
  address="$("${compose[@]}" port nginx 8080 | head -n 1)"
  if [[ -z "$address" ]]; then
    echo "Unable to resolve the local edge port." >&2
    return 1
  fi
  case "$address" in
    0.0.0.0:*)
      address="127.0.0.1:${address##*:}"
      ;;
    "[::]:"*)
      address="127.0.0.1:${address##*:}"
      ;;
  esac
  printf 'http://%s\n' "$address"
}

restore_previous_images() {
  local variable
  for variable in "${image_variables[@]}"; do
    printf -v "$variable" '%s' "${previous_images[$variable]}"
    export "$variable"
  done
  SOURCE_SHA="$previous_source"
  APP_DEPLOYMENT_ENV="$(
    [[ "$DEPLOYMENT_TARGET" == "production-readonly" ]] \
      && printf production \
      || printf staging
  )"
  export SOURCE_SHA APP_DEPLOYMENT_ENV
}

rollback() {
  local exit_code=$?
  if [[ "$rollback_started" == "true" ]]; then
    exit "$exit_code"
  fi
  rollback_started=true
  trap - ERR

  if [[ "$candidate_started" != "true" ]]; then
    exit "$exit_code"
  fi

  if [[ "$previous_complete" != "true" ]]; then
    echo "Candidate failed without a complete previous release; stopping it." >&2
    "${compose[@]}" stop \
      web daphne realtime_bridge nginx db-backup statsd-exporter || true
    exit "$exit_code"
  fi

  echo "Candidate verification failed; restoring previous immutable images." >&2
  restore_previous_images

  if [[ "$static_snapshot_created" == "true" ]]; then
    "${compose_all[@]}" run --rm --no-deps static-maintenance \
      /bin/sh -ec \
      'find /app/static -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar -xzf "/releases/'"${CHANGE_ID}"'/static-before.tgz" -C /app/static'
  fi

  "${compose[@]}" up -d --no-build --wait \
    postgres redis nats centrifugo web daphne realtime_bridge \
    nginx db-backup statsd-exporter

  if [[ "$previous_source" =~ ^[0-9a-f]{40}$ ]]; then
    previous_local_url="$(local_edge_url)"
    python3 operations/verify_release_identity.py \
      --base-url "$previous_local_url" \
      --source-sha "$previous_source" \
      --image-digest "${previous_images[BACKEND_IMAGE]}" \
      --output "${release_dir}/rollback-local-evidence.json"
  fi
  exit "$exit_code"
}
trap rollback ERR

"${compose[@]}" up -d --no-build --wait postgres redis nats centrifugo
"${compose_all[@]}" run --rm --no-deps backup-init

"${compose[@]}" run --rm --no-deps db-backup \
  /bin/sh -ec 'test -d /backups && test -w /backups && test -d /offhost && test -w /offhost'

backup_prefix="predeploy-${SOURCE_SHA:0:12}"
"${compose[@]}" run --rm --no-deps \
  -e BACKUP_NAME_PREFIX="$backup_prefix" \
  db-backup \
  /bin/sh /usr/local/bin/backup-once.sh \
  | tee "${release_dir}/backup-evidence.txt"

"${compose_all[@]}" run --rm --no-deps static-maintenance \
  /bin/sh -ec \
  'tar -czf "/releases/'"${CHANGE_ID}"'/static-before.tgz" -C /app/static .'
static_snapshot_created=true

"${compose_all[@]}" run --rm --no-deps static-init
"${compose_all[@]}" run --rm --no-deps \
  -e ALLOW_SCHEMA_MIGRATIONS="$ALLOW_SCHEMA_MIGRATIONS" \
  release-init \
  | tee "${release_dir}/migration-evidence.txt"

disabled_services=(
  canonical-outbox-publisher
  celery_worker
  celery_beat
  celery-flower
  chart-data-publisher
  demo-event-publisher
  simulated-execution-consumer
)
"${compose_all[@]}" stop "${disabled_services[@]}" || true
"${compose_all[@]}" rm -f "${disabled_services[@]}" || true

candidate_started=true
"${compose[@]}" up -d --no-build --wait \
  web daphne realtime_bridge nginx db-backup statsd-exporter

active_services=(
  web
  daphne
  realtime_bridge
  nginx
  db-backup
  statsd-exporter
  postgres
  redis
  nats
  centrifugo
)
for service in "${active_services[@]}"; do
  container="$("${compose_all[@]}" ps -q "$service")"
  if [[ -z "$container" ]]; then
    printf 'Service %s did not start.\n' "$service" >&2
    exit 1
  fi
  variable=""
  case "$service" in
    web|daphne|realtime_bridge) variable=BACKEND_IMAGE ;;
    nginx) variable=EDGE_IMAGE ;;
    db-backup|postgres) variable=POSTGRES_IMAGE ;;
    redis) variable=REDIS_IMAGE ;;
    nats) variable=NATS_IMAGE ;;
    centrifugo) variable=CENTRIFUGO_IMAGE ;;
    statsd-exporter) variable=STATSD_EXPORTER_IMAGE ;;
  esac
  observed="$(docker inspect --format '{{.Config.Image}}' "$container")"
  if [[ "$observed" != "${!variable}" ]]; then
    printf 'Image mismatch for %s: %s\n' "$service" "$observed" >&2
    exit 1
  fi
done

for service in "${disabled_services[@]}"; do
  if [[ -n "$("${compose_all[@]}" ps -q "$service" 2>/dev/null || true)" ]]; then
    printf 'Disabled service is still running: %s\n' "$service" >&2
    exit 1
  fi
done

candidate_local_url="$(local_edge_url)"
python3 operations/verify_release_identity.py \
  --base-url "$candidate_local_url" \
  --source-sha "$SOURCE_SHA" \
  --image-digest "$BACKEND_IMAGE" \
  --output "${release_dir}/candidate-local-evidence.json"

python3 operations/verify_release_identity.py \
  --base-url "$PUBLIC_BASE_URL" \
  --source-sha "$SOURCE_SHA" \
  --image-digest "$BACKEND_IMAGE" \
  --output "${release_dir}/candidate-public-evidence.json"

{
  printf 'SOURCE_SHA=%q\n' "$SOURCE_SHA"
  printf 'BACKEND_IMAGE=%q\n' "$BACKEND_IMAGE"
  printf 'EDGE_IMAGE=%q\n' "$EDGE_IMAGE"
  printf 'DEPLOYMENT_TARGET=%q\n' "$DEPLOYMENT_TARGET"
  printf 'CHANGE_ID=%q\n' "$CHANGE_ID"
  printf 'DEPLOYED_AT=%q\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "${release_dir}/candidate.env"

trap - ERR
printf 'DEPLOYMENT_RESULT=PASS\n'
