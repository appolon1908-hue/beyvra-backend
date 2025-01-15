# FX/celery.py
# from __future__ import absolute_import, unicode_literals
# import os
# from celery import Celery

# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FX.settings")

# app = Celery("FX")
# app.config_from_object("django.conf:settings", namespace="CELERY")
# app.autodiscover_tasks(['wsnotifications'])  # Replace 'core' with the name of your app

# @app.task(bind=True)
# def debug_task(self):
#     print('Request: {0!r}'.format(self.request))

# path/to/your/proj/src/cfehome/celery.py
import os
from celery import Celery
from celery.schedules import crontab
from wsnotifications.tasks import periodic_price_updates

# set the default Django settings module for the 'celery' program.
# this is also used in manage.py
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FX.settings')

app = Celery('FX')



app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks(["wsnotifications"])

