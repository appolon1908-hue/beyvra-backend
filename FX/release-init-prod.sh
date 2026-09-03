#!/bin/sh
set -eu

python3 manage.py wait_for_db
python3 manage.py wait_for_redis
python3 manage.py check --deploy
python3 manage.py makemigrations --check --dry-run

plan_file="$(mktemp)"
trap 'rm -f "$plan_file"' EXIT HUP INT TERM
python3 manage.py migrate --plan | tee "$plan_file"

case "${DEPLOYMENT_ENV:-local}" in
  staging|production)
    if [ "${ALLOW_SCHEMA_MIGRATIONS:-false}" != "true" ] \
      && ! grep -Fq "No planned migration operations." "$plan_file"; then
      echo "Schema changes require ALLOW_SCHEMA_MIGRATIONS=true." >&2
      exit 1
    fi
    ;;
esac

# The runtime connection is database-enforced read-only. Only this reviewed,
# one-shot release process may create a write-capable Django process.
env DEPLOYMENT_READ_ONLY=false python3 manage.py migrate --noinput
env DEPLOYMENT_READ_ONLY=false python3 manage.py collectstatic --no-input
