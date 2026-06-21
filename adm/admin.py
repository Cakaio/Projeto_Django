from django.contrib import admin
from .models import Categoria, Lancamento


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'tipo', 'ativo')
    list_filter = ('tipo', 'ativo')


@admin.register(Lancamento)
class LancamentoAdmin(admin.ModelAdmin):
    list_display = ('data', 'tipo', 'categoria', 'valor', 'origem', 'criado_por')
    list_filter = ('tipo', 'origem', 'categoria')
    date_hierarchy = 'data'
