from django.contrib import admin
from .models import Categoria, Conta, Evento, Lancamento, RecargaCartao, TetoArea


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'tipo', 'ativo')
    list_filter = ('tipo', 'ativo')


@admin.register(Lancamento)
class LancamentoAdmin(admin.ModelAdmin):
    list_display = ('data', 'tipo', 'categoria', 'valor', 'conta', 'area', 'evento',
                    'origem', 'criado_por')
    list_filter = ('tipo', 'origem', 'categoria', 'conta', 'area')
    date_hierarchy = 'data'


@admin.register(Conta)
class ContaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'tipo', 'controla_saldo', 'responsavel', 'saldo', 'ativo')
    list_filter = ('tipo', 'controla_saldo', 'ativo')
    search_fields = ('nome',)


@admin.register(RecargaCartao)
class RecargaCartaoAdmin(admin.ModelAdmin):
    list_display = ('data', 'conta', 'valor', 'area', 'carregado_por', 'motivo')
    list_filter = ('conta', 'area')
    date_hierarchy = 'data'


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'data', 'teto', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)


@admin.register(TetoArea)
class TetoAreaAdmin(admin.ModelAdmin):
    list_display = ('area', 'competencia', 'valor', 'definido_por', 'atualizado_em')
    list_filter = ('area',)
