"""App do próprio projeto.

Existe por um motivo só: dar casa às checagens de sistema em `TESTE/checks.py`,
que precisam de um `AppConfig.ready()` para se registrarem. Sem models, sem
templates e sem migrations.
"""
from django.apps import AppConfig


class NucleoConfig(AppConfig):
    name = 'TESTE'
    label = 'nucleo'
    verbose_name = 'Núcleo do projeto'

    def ready(self):
        from . import checks  # noqa: F401  (o import é o registro)
