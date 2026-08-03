#!/bin/sh
set -eu
: "${BACKUP_RESTIC_REPOSITORY:?set the Restic repository}"
: "${RESTIC_PASSWORD_FILE:?set the protected Restic password file}"
: "${RESTIC_SNAPSHOT:?set a snapshot id}"
: "${RESTORE_DIRECTORY:?set a disposable restore directory}"
mkdir -p "$RESTORE_DIRECTORY"
RESTIC_PASSWORD_FILE="$RESTIC_PASSWORD_FILE" restic restore "$RESTIC_SNAPSHOT" --target "$RESTORE_DIRECTORY"
