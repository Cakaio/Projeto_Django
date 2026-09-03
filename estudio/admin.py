from django.contrib import admin

from .models import Asset, Documento, Elemento, Pagina


class PaginaInline(admin.TabularInline):
    model = Pagina
    extra = 0
    fields = ['ordem', 'preset', 'cor_de_fundo']


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'tipo', 'total_paginas', 'revista', 'criado_por', 'atualizado_em']
    list_filter = ['tipo']
    search_fields = ['titulo']
    inlines = [PaginaInline]


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ['nome', 'categoria', 'apelido', 'enviado_por', 'criado_em']
    list_filter = ['categoria']
    search_fields = ['nome', 'apelido']


@admin.register(Elemento)
class ElementoAdmin(admin.ModelAdmin):
    """Só para depurar layout torto — a edição de verdade é no estúdio."""
    list_display = ['pagina', 'tipo', 'x', 'y', 'largura', 'altura', 'z', 'travado']
    list_filter = ['tipo', 'travado']
