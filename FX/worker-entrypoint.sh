#!/bin/bash
set -e
# just start a single worker. You can increase number of workers by changing --concurrency parameter.
celery -A FX worker -E
