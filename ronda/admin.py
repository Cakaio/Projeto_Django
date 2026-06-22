# ronda/admin.py
from django.contrib import admin
from .models import LocalRonda, ConfiguracaoRondaSabado, HorarioRonda, EscalaRonda, ScoreRonda

admin.site.register(LocalRonda)
admin.site.register(ConfiguracaoRondaSabado)
admin.site.register(HorarioRonda)
admin.site.register(EscalaRonda)
admin.site.register(ScoreRonda)
