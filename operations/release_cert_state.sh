#!/usr/bin/env bash
# Backup and runtime transition helpers for Beyvra certification.

cert_verify_backup_evidence() {
  local local_file offhost_file basename_file
  local_file="$(sed -n 's/^BACKUP_FILE=//p' "${cert_release_dir}/backup-evidence.txt" | tail -n 1)"
  offhost_file="$(sed -n 's/^BACKUP_OFFHOST_FILE=//p' "${cert_release_dir}/backup-evidence.txt" | tail -n 1)"
  [[ "$local_file" =~ ^/backups/[A-Za-z0-9._-]+\.dump$ ]]
  [[ "$offhost_file" =~ ^/offhost/[A-Za-z0-9._-]+\.dump$ ]]
  basename_file="${local_file##*/}"
  "${cert_compose[@]}" run --rm --no-deps db-backup /bin/sh -ec \
    "cd /backups && pg_restore --list '$basename_file' >/dev/null && sha256sum -c '${basename_file}.sha256'"
  "${cert_compose[@]}" run --rm --no-deps db-backup /bin/sh -ec \
    "cd /offhost && pg_restore --list '$basename_file' >/dev/null && sha256sum -c '${basename_file}.sha256'"
  grep -Fq "No planned migration operations." "${cert_release_dir}/migration-evidence.txt"
}

cert_save_runtime() {
  local output=$1 variable
  {
    printf 'SOURCE_SHA=%q\n' "$SOURCE_SHA"
    printf 'APP_DEPLOYMENT_ENV=%q\n' "$APP_DEPLOYMENT_ENV"
    for variable in "${cert_image_variables[@]}"; do
      printf '%s=%q\n' "$variable" "${!variable}"
    done
  } >"$output"
}

cert_export_runtime() {
  local path=$1 variable
  # shellcheck disable=SC1090
  source "$path"
  export SOURCE_SHA APP_DEPLOYMENT_ENV
  for variable in "${cert_image_variables[@]}"; do export "$variable"; done
}

cert_stop_disabled() {
  "${cert_compose_all[@]}" stop "${cert_disabled_services[@]}" || true
  "${cert_compose_all[@]}" rm -f "${cert_disabled_services[@]}" || true
}

cert_start_runtime() {
  cert_stop_disabled
  "${cert_compose[@]}" up -d --no-build --wait \
    postgres redis nats centrifugo web daphne realtime_bridge nginx db-backup statsd-exporter
}

cert_restore_static_snapshot() {
  "${cert_compose_all[@]}" run --rm --no-deps static-maintenance /bin/sh -ec \
    'find /app/static -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar -xzf "/releases/'"${CHANGE_ID}"'/static-before.tgz" -C /app/static'
}

cert_start_candidate_release() {
  "${cert_compose_all[@]}" run --rm --no-deps static-init
  "${cert_compose_all[@]}" run --rm --no-deps \
    -e ALLOW_SCHEMA_MIGRATIONS=false release-init \
    >"${cert_release_dir}/rollback-reapply-migration-evidence.txt"
  cert_start_runtime
}
