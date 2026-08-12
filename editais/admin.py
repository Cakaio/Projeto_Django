from django.contrib import admin

from .models import Edital, FonteEdital, PalavraChave


@admin.register(FonteEdital)
class FonteEditalAdmin(admin.ModelAdmin):
    list_display = ('nome', 'tipo', 'ativo', 'ultima_coleta', 'itens_ultima_coleta', 'saudavel')
    list_filter = ('tipo', 'ativo')
    search_fields = ('nome', 'url')
    readonly_fields = ('ultima_coleta', 'ultimo_erro', 'itens_ultima_coleta')


@admin.register(PalavraChave)
class PalavraChaveAdmin(admin.ModelAdmin):
    list_display = ('termo', 'peso', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('termo',)
    list_editable = ('peso', 'ativo')


@admin.register(Edital)
class EditalAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'status', 'relevancia', 'prazo', 'fonte', 'responsavel')
    list_filter = ('status', 'origem', 'fonte')
    search_fields = ('titulo', 'descricao', 'link')
    date_hierarchy = 'criado_em'
    # A chave é derivada do link e a relevância é conta do robô: editar à mão
    # aqui só criaria divergência com o que a varredura vai recalcular.
    readonly_fields = ('chave', 'relevancia', 'termos_encontrados', 'criado_em', 'atualizado_em')
