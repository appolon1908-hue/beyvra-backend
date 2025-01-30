from django.apps import AppConfig


class WsnotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wsnotifications'
    
    def ready(self):
        import wsnotifications.signals  # Import the signals to connect them

    