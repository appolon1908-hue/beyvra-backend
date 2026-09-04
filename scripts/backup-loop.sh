#!/bin/sh
set -eu
umask 077

: "${BACKUP_OFFHOST_DIR:?BACKUP_OFFHOST_DIR is required}"
: "${BACKUP_RETENTION_DAYS:?BACKUP_RETENTION_DAYS is required}"
: "${BACKUP_INTERVAL_SECONDS:?BACKUP_INTERVAL_SECONDS is required}"

while true; do
  /bin/sh /usr/local/bin/backup-once.sh

  find /backups -type f \
    \( -name "${PGDATABASE}-*.dump" -o -name "${PGDATABASE}-*.dump.sha256" \) \
    -mtime "+${BACKUP_RETENTION_DAYS}" -delete
  find "$BACKUP_OFFHOST_DIR" -type f \
    \( -name "${PGDATABASE}-*.dump" -o -name "${PGDATABASE}-*.dump.sha256" \) \
    -mtime "+${BACKUP_RETENTION_DAYS}" -delete

  sleep "${BACKUP_INTERVAL_SECONDS}"
done
