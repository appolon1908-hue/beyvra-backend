#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: CONFIRM_RESTORE=restore-${DB_NAME} $0 backups/<file>.dump" >&2
  exit 2
fi

expected="restore-${DB_NAME}"
if [ "${CONFIRM_RESTORE:-}" != "${expected}" ]; then
  echo "Refusing restore. Set CONFIRM_RESTORE=${expected} after verifying the target." >&2
  exit 3
fi

backup_file="$1"
case "${backup_file}" in
  backups/*.dump) ;;
  *) echo "Backup must be a .dump file inside backups/." >&2; exit 4 ;;
esac

docker compose exec -T postgres pg_restore \
  --clean --if-exists --no-owner --no-acl \
  --username "${DB_USER}" --dbname "${DB_NAME}" < "${backup_file}"
