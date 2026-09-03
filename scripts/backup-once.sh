#!/bin/sh
set -eu
umask 077

: "${BACKUP_OFFHOST_DIR:?BACKUP_OFFHOST_DIR is required}"
: "${PGDATABASE:?PGDATABASE is required}"
: "${PGUSER:?PGUSER is required}"

if [ ! -d "$BACKUP_OFFHOST_DIR" ] || [ ! -w "$BACKUP_OFFHOST_DIR" ]; then
  echo "The off-host backup directory is unavailable or not writable." >&2
  exit 1
fi

prefix="${BACKUP_NAME_PREFIX:-${PGDATABASE}}"
case "$prefix" in
  *[!A-Za-z0-9._-]*|"")
    echo "BACKUP_NAME_PREFIX contains unsupported characters" >&2
    exit 1
    ;;
esac

mkdir -p /backups
chmod 700 /backups

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="/backups/${prefix}-${stamp}.dump"
checksum="${destination}.sha256"
temporary="${destination}.tmp"
checksum_temporary="${checksum}.tmp"
offhost_destination="${BACKUP_OFFHOST_DIR}/$(basename "$destination")"
offhost_checksum="${offhost_destination}.sha256"

for path in "$destination" "$checksum" "$offhost_destination" "$offhost_checksum"; do
  if [ -e "$path" ]; then
    echo "Refusing to overwrite an existing backup: $path" >&2
    exit 1
  fi
done

cleanup() {
  rm -f \
    "$temporary" \
    "$checksum_temporary" \
    "${offhost_destination}.tmp" \
    "${offhost_checksum}.tmp"
}
trap cleanup EXIT HUP INT TERM

pg_dump --format=custom --no-owner --no-acl --file="$temporary"
pg_restore --list "$temporary" >/dev/null
mv "$temporary" "$destination"
(cd /backups && sha256sum "$(basename "$destination")") > "$checksum_temporary"
mv "$checksum_temporary" "$checksum"

cp "$destination" "${offhost_destination}.tmp"
cp "$checksum" "${offhost_checksum}.tmp"
cmp -s "$destination" "${offhost_destination}.tmp"
mv "${offhost_destination}.tmp" "$offhost_destination"
mv "${offhost_checksum}.tmp" "$offhost_checksum"
(
  cd "$BACKUP_OFFHOST_DIR"
  sha256sum -c "$(basename "$offhost_checksum")"
)

trap - EXIT HUP INT TERM
printf 'BACKUP_FILE=%s\n' "$destination"
printf 'BACKUP_CHECKSUM=%s\n' "$checksum"
printf 'BACKUP_OFFHOST_FILE=%s\n' "$offhost_destination"
