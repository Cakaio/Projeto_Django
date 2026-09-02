from django.contrib import admin

from .models import Colecao, Documento


@admin.register(Colecao)
class ColecaoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'slug', 'ordem', 'ativo', 'total_documentos']
    list_filter = ['ativo']
    search_fields = ['nome', 'descricao']
    prepopulated_fields = {'slug': ('nome',)}


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'colecao', 'ano', 'de_quem', 'cargo_pretendido',
                    'resultado', 'enviado_por']
    list_filter = ['colecao', 'ano', 'resultado']
    search_fields = ['titulo', 'descricao', 'nome_avulso', 'cargo_pretendido',
                     'pessoa__first_name', 'pessoa__last_name']
    autocomplete_fields = ['pessoa', 'enviado_por']
