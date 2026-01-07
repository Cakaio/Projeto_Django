from django.contrib import admin
from .models import Voluntario, PresencaVoluntario
from django.contrib.auth.admin import UserAdmin

campos = list(UserAdmin.fieldsets)
campos.append(("Informações Adicionais", {'fields': ('apelido', 'area', 'data_nascimento', 'celular', 'rg', 'foto', 'data_entrada_projeto', 'data_saida_projeto')}))

UserAdmin.fieldsets = tuple(campos)

# Register your models here.
admin.site.register(Voluntario,UserAdmin)
admin.site.register(PresencaVoluntario)