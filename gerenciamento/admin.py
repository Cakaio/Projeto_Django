from django.contrib import admin

from .models import CienciaPauta, ComentarioPauta, Pauta


class ComentarioPautaInline(admin.TabularInline):
    model = ComentarioPauta
    extra = 0
    readonly_fields = ["autor", "criado_em"]


@admin.register(Pauta)
class PautaAdmin(admin.ModelAdmin):
    list_display = ["titulo", "status", "grupo", "emitido_por_area", "ddl", "criado_por"]
    list_filter = ["status", "grupo", "emitido_por_area"]
    search_fields = ["titulo", "descricao"]
    autocomplete_fields = ["criado_por"]
    inlines = [ComentarioPautaInline]


@admin.register(ComentarioPauta)
class ComentarioPautaAdmin(admin.ModelAdmin):
    list_display = ["pauta", "autor", "criado_em"]
    search_fields = ["texto", "autor__username", "pauta__titulo"]


@admin.register(CienciaPauta)
class CienciaPautaAdmin(admin.ModelAdmin):
    list_display = ["pauta", "voluntario", "ciente_em", "ocultada"]
    list_filter = ["ocultada"]
