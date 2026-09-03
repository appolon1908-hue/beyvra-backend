#!/bin/sh
set -eu

python3 manage.py wait_for_db
python3 manage.py wait_for_redis

exec gunicorn FX.wsgi:application -c gunicorn_conf.py
