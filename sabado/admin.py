from django.contrib import admin
from .models import DisponibilidadeVoluntario, Sabado, FaixaHorarioAjuda

# Register your models here.
@admin.register(Sabado)
class SabadoAdmin(admin.ModelAdmin):
    list_display = ['data', 'tema']
    search_fields = ['tema']

@admin.register(DisponibilidadeVoluntario)
class DisponibilidadeVoluntarioAdmin(admin.ModelAdmin):
    list_display = ['sabado', 'voluntario', 'vai_ao_projeto']
    search_fields = ['voluntario__first_name', 'voluntario__last_name']
    list_filter = ['sabado', 'vai_ao_projeto']
    filter_horizontal = ['pode_ajudar']

@admin.register(FaixaHorarioAjuda)
class FaixaHorarioAjudaAdmin(admin.ModelAdmin):
    list_display = ['descricao']
    search_fields = ['descricao']