#!/bin/sh
set -eu

PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-multiproc
export PROMETHEUS_MULTIPROC_DIR
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
find "$PROMETHEUS_MULTIPROC_DIR" -mindepth 1 -maxdepth 1 -type f -delete

python3 manage.py wait_for_db
python3 manage.py wait_for_redis

# The management commands import application metrics. Remove their exited
# process files so the Gunicorn registry begins from an exact zero baseline.
find "$PROMETHEUS_MULTIPROC_DIR" -mindepth 1 -maxdepth 1 -type f -delete

exec gunicorn FX.wsgi:application -c gunicorn_conf.py
