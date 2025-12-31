from django.contrib import admin
from .models import Atendido, Familia, PresencaAtendido

# Register your models here.
admin.site.register(Atendido)
admin.site.register(Familia)
admin.site.register(PresencaAtendido)