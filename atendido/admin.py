from django.contrib import admin
from .models import Atendido, Familia, PresencaAtendido

# Register your models here.
admin.site.register(Atendido)
admin.site.register(Familia)

@admin.register(PresencaAtendido)
class PresencaAtendidoAdmin(admin.ModelAdmin):
    list_display = ['atendido', 'data', 'registrado_por']
    list_filter = ['data']