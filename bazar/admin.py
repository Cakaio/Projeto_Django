"""Configuração do Bazar pelo admin.

A configuração acontece UMA vez por ano, com calma, antes do evento — cota,
categorias e estoque inicial. Inventar telas de CRUD para isso seria trabalho
para ganhar pouco: o admin já faz, já valida e já registra quem mexeu.

A tela que precisou ser feita à mão é a de atendimento, que roda com fila na
frente. Essa não cabe no admin.
"""
from django.contrib import admin

from .models import Bazar, Categoria, ItemRetirada, Retirada, SalaDoBazar


class CategoriaInline(admin.TabularInline):
    model = Categoria
    extra = 6          # o PRD lista seis categorias; já vêm as linhas prontas
    fields = ("ordem", "nome", "pontos", "estoque_inicial", "ativo")
    ordering = ("ordem", "nome")


class SalaDoBazarInline(admin.TabularInline):
    """As salas físicas, configuradas junto do Bazar.

    Sem nenhuma cadastrada, a tela de atendimento não oferece escolha e a
    coluna "sala" do relatório volta a ficar vazia — que é o problema que a
    lista veio resolver.
    """
    model = SalaDoBazar
    extra = 3          # três é o número que a coordenação usa na prática
    fields = ("ordem", "nome", "ativo")
    ordering = ("ordem", "nome")


@admin.register(Bazar)
class BazarAdmin(admin.ModelAdmin):
    list_display = ("nome", "data", "etapa", "cota_inicial", "total_retiradas")
    list_filter = ("etapa", "data")
    inlines = [CategoriaInline, SalaDoBazarInline]
    readonly_fields = ("criado_por", "criado_em")

    @admin.display(description="Retiradas")
    def total_retiradas(self, obj):
        return obj.retiradas.filter(finalizada_em__isnull=False).count()

    def save_model(self, request, obj, form, change):
        if not change:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)


class ItemRetiradaInline(admin.TabularInline):
    model = ItemRetirada
    extra = 0
    # Valor e total são cópia do momento da retirada: reescrever aqui
    # falsificaria o histórico que o relatório usa.
    readonly_fields = ("categoria", "quantidade", "pontos_unitarios", "pontos_total")
    can_delete = False


@admin.register(Retirada)
class RetiradaAdmin(admin.ModelAdmin):
    """Só leitura e correção pontual.

    Existe para a coordenação resolver problema DURANTE o Bazar — alguém
    registrado errado, retirada duplicada por engano. Criar retirada por aqui
    não faz sentido: a conta de pontos mora na tela de atendimento.
    """
    list_display = ("atendido", "bazar", "etapa", "pontos_usados",
                    "total_pecas", "conferido_por", "finalizada_em")
    list_filter = ("bazar", "etapa", "atendido__sala")
    search_fields = ("atendido__nome",)
    # Sem `autocomplete_fields`: ele exigiria declarar search_fields no
    # AtendidoAdmin, que é de outro app. Um select com a lista de atendidos
    # basta aqui — esta tela é para correção pontual, não para uso na fila.
    inlines = [ItemRetiradaInline]
    readonly_fields = ("cota_no_momento", "criado_em")

    @admin.display(description="Pontos")
    def pontos_usados(self, obj):
        return obj.pontos_usados

    @admin.display(description="Peças")
    def total_pecas(self, obj):
        return obj.total_pecas
