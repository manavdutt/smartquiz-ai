from django.apps import AppConfig

class McqAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mcq_app'

    def ready(self):
        import mcq_app.signals  # signals connect hote hain yahan