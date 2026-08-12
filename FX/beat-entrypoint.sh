#!/bin/sh
set -e
celery -A FX beat --loglevel=info
