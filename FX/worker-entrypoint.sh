#!/bin/bash
set -e
# just start a single worker. You can increase number of workers by changing --concurrency parameter.
# celery -A FX worker -l info --pool=solo
celery -A FX worker --loglevel=INFO --concurrency 1 -P solo