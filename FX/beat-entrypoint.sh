#!/bin/bash
set -e
celery -A FX beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
