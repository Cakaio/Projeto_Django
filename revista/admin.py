from django.contrib import admin

from .models import Revista, SecaoRevista


class SecaoRevistaInline(admin.TabularInline):
    model = SecaoRevista
    extra = 0
    fields = ('ordem', 'incluir', 'titulo', 'sala', 'competencia', 'atividade')
    ordering = ('ordem', 'pk')


@admin.register(Revista)
class RevistaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'periodo_inicio', 'periodo_fim', 'status',
                    'link_publico_ativo', 'link_expira_em', 'criado_por')
    list_filter = ('status', 'link_publico_ativo')
    search_fields = ('titulo', 'subtitulo')
    date_hierarchy = 'periodo_fim'
    inlines = [SecaoRevistaInline]
    # O token é a senha do link do doador: se mudar, o endereço já enviado
    # deixa de abrir. Trocar é decisão de tela ("revogar"), não de digitação.
    readonly_fields = ('token', 'criado_em', 'atualizado_em')


@admin.register(SecaoRevista)
class SecaoRevistaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'revista', 'sala', 'ordem', 'incluir')
    list_filter = ('incluir', 'sala', 'revista')
    search_fields = ('titulo', 'texto')
