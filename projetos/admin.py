from django.contrib import admin

from .models import Demanda, RegistroDemanda
from .servicos import sincronizar_retorno


class RegistroInline(admin.TabularInline):
    model = RegistroDemanda
    extra = 0
    fields = ('data', 'tipo', 'descricao', 'autor')


@admin.register(Demanda)
class DemandaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'area', 'status', 'retorno', 'prioridade',
                    'responsavel', 'atualizado_em')
    list_filter = ('area', 'status', 'retorno', 'prioridade')
    search_fields = ('titulo', 'o_que_pediram', 'o_que_fizemos')
    inlines = [RegistroInline]


@admin.register(RegistroDemanda)
class RegistroDemandaAdmin(admin.ModelAdmin):
    list_display = ('demanda', 'data', 'tipo', 'autor')
    list_filter = ('tipo', 'data', 'demanda__area')
    search_fields = ('demanda__titulo', 'descricao')
    date_hierarchy = 'data'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Mesma coerência da ficha: histórico e status da demanda não podem
        # contar histórias diferentes só porque o registro entrou pelo admin.
        sincronizar_retorno(obj.demanda, obj)
