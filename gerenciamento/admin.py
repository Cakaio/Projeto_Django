from django.contrib import admin

from .models import CienciaPauta, ComentarioPauta, Pauta, Reuniao


class ComentarioPautaInline(admin.TabularInline):
    model = ComentarioPauta
    extra = 0
    readonly_fields = ["autor", "criado_em"]


@admin.register(Pauta)
class PautaAdmin(admin.ModelAdmin):
    list_display = [
        "titulo", "status", "prioridade", "grupo",
        "emitido_por_area", "prazo_ddl", "criado_por",
    ]
    list_filter = ["status", "prioridade", "grupo", "emitido_por_area"]
    search_fields = ["titulo", "descricao", "etiquetas"]
    autocomplete_fields = ["criado_por"]
    filter_horizontal = ["responsaveis"]
    inlines = [ComentarioPautaInline]


@admin.register(Reuniao)
class ReuniaoAdmin(admin.ModelAdmin):
    list_display = ["titulo", "data_reuniao", "grupo"]
    list_filter = ["grupo", "data_reuniao"]
    search_fields = ["titulo", "descricao", "grupo__nome"]


@admin.register(ComentarioPauta)
class ComentarioPautaAdmin(admin.ModelAdmin):
    list_display = ["pauta", "autor", "criado_em"]
    search_fields = ["texto", "autor__username", "pauta__titulo"]
    filter_horizontal = ["mencoes"]


@admin.register(CienciaPauta)
class CienciaPautaAdmin(admin.ModelAdmin):
    list_display = ["pauta", "voluntario", "ciente_em"]
