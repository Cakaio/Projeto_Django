from django.apps import AppConfig


class ParceirosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parceiros'
    verbose_name = 'Parceiros (CR/RE)'

    def ready(self):
        from . import signals  # noqa: F401  (registra os sinais)
