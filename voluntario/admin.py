from django.contrib import admin
from .models import Talento, Voluntario, PresencaVoluntario
from django.contrib.auth.admin import UserAdmin

# Register your models here.
admin.site.register(PresencaVoluntario)

@admin.register(Talento)
class TalentoAdmin(admin.ModelAdmin):
    list_display = ['talento']
    search_fields = ['talento']

@admin.register(Voluntario)
class VoluntarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Informações Adicionais", {'fields': ('apelido', 'area', 'data_nascimento', 'celular', 'rg', 'foto', 'talentos')}),
    )
    filter_horizontal = ['talentos']