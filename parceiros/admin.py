from django.contrib import admin

from .models import Contribuicao, Interacao, Parceiro


class ContribuicaoInline(admin.TabularInline):
    model = Contribuicao
    extra = 0
    fields = ('competencia', 'valor', 'data_recebimento', 'forma', 'lancamento')
    readonly_fields = ('lancamento',)


class InteracaoInline(admin.TabularInline):
    model = Interacao
    extra = 0
    fields = ('data', 'tipo', 'descricao', 'autor')


@admin.register(Parceiro)
class ParceiroAdmin(admin.ModelAdmin):
    list_display = ('nome', 'responsavel', 'status', 'total_arrecadado')
    list_filter = ('status', 'responsavel')
    search_fields = ('nome', 'email', 'telefone', 'documento')
    inlines = [ContribuicaoInline, InteracaoInline]


@admin.register(Contribuicao)
class ContribuicaoAdmin(admin.ModelAdmin):
    list_display = ('parceiro', 'competencia', 'valor', 'data_recebimento', 'forma', 'lancamento')
    list_filter = ('competencia', 'forma', 'parceiro__responsavel')
    search_fields = ('parceiro__nome',)
    date_hierarchy = 'competencia'
    readonly_fields = ('lancamento',)


@admin.register(Interacao)
class InteracaoAdmin(admin.ModelAdmin):
    list_display = ('parceiro', 'data', 'tipo', 'autor')
    list_filter = ('tipo', 'data')
    search_fields = ('parceiro__nome', 'descricao')
