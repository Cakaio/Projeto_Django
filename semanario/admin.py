from django.contrib import admin
from .models import Semanario, Material

class MaterialInline(admin.TabularInline):
    model = Material
    extra = 1  # número de linhas em branco para adicionar
    fields = ("nome", "quantidade", "unidade")

class SemanarioAdmin(admin.ModelAdmin):
    list_display = ("sala", "data", "atividade", "responsavel")
    inlines = [MaterialInline]

admin.site.register(Semanario, SemanarioAdmin)
