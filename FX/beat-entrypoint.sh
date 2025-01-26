#!/bin/bash
set -e
celery -A FX beat --loglevel=info