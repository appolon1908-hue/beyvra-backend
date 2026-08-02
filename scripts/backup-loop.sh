#!/bin/sh
set -eu

mkdir -p /backups
while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  destination="/backups/${PGDATABASE}-${stamp}.dump"
  temporary="${destination}.tmp"
  pg_dump --format=custom --no-owner --no-acl --file="${temporary}"
  mv "${temporary}" "${destination}"
  find /backups -type f -name "${PGDATABASE}-*.dump" -mtime "+${BACKUP_RETENTION_DAYS}" -delete
  sleep "${BACKUP_INTERVAL_SECONDS}"
done
