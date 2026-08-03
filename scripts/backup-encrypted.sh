#!/bin/sh
set -eu
: "${BACKUP_RESTIC_REPOSITORY:?set an approved Restic repository}"
: "${RESTIC_PASSWORD_FILE:?set a protected Restic password file}"
: "${PGHOST:?set PostgreSQL connection settings}"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
dump="$tmp_dir/codestra-$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump --format=custom --file="$dump"
RESTIC_PASSWORD_FILE="$RESTIC_PASSWORD_FILE" restic backup "$dump" --tag codestra-postgres
RESTIC_PASSWORD_FILE="$RESTIC_PASSWORD_FILE" restic forget --tag codestra-postgres --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune
