#!/bin/sh
set -eu

python3 manage.py wait_for_db
python3 manage.py wait_for_redis
python3 manage.py check --deploy
python3 manage.py makemigrations --check --dry-run

plan_file="$(mktemp)"
trap 'rm -f "$plan_file"' EXIT HUP INT TERM
python3 manage.py migrate --plan | tee "$plan_file"

pending_migrations=true
if grep -Fq "No planned migration operations." "$plan_file"; then
  pending_migrations=false
fi

case "${DEPLOYMENT_ENV:-local}" in
  staging|production)
    if [ "$pending_migrations" = true ] \
      && [ "${ALLOW_SCHEMA_MIGRATIONS:-false}" != "true" ]; then
      echo "Schema changes require ALLOW_SCHEMA_MIGRATIONS=true." >&2
      exit 1
    fi
    ;;
esac

# A zero-change read-only release must not invoke Django's migrate command at
# all: even an empty migration plan can run post_migrate handlers that write.
if [ "$pending_migrations" = true ]; then
  env DEPLOYMENT_READ_ONLY=false python3 manage.py migrate --noinput
else
  echo "No planned migration operations; migration execution skipped."
fi

# Static collection is allowed, but it keeps the database read-only guard.
python3 manage.py collectstatic --no-input
