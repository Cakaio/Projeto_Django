from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export.formats import base_formats
from import_export import resources
from .models import Item, Local, Movimentacao, Pedido


@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "cidade", "numero_contato", "ativo")
    list_filter = ("tipo", "ativo", "cidade")
    search_fields = ("nome", "localizacao", "cidade", "numero_contato", "email")
    ordering = ("nome",)


class ItemResource(resources.ModelResource):
    class Meta:
        model = Item
        fields = ('id', 'nome', 'descricao', 'categoria', 'unidade', 'quantidade_minima', 'ativo')


class MovimentacaoResource(resources.ModelResource):
    class Meta:
        model = Movimentacao
        fields = ('id', 'item', 'tipo', 'quantidade', 'observacao', 'registrado_por', 'sabado', 'criado_em')


class MovimentacaoInline(admin.TabularInline):
    model = Movimentacao
    extra = 1
    readonly_fields = ['criado_em']


@admin.register(Item)
class ItemAdmin(ImportExportModelAdmin):
    resource_class = ItemResource
    formats = [base_formats.XLSX, base_formats.CSV]

    list_display = ['nome', 'categoria', 'unidade', 'quantidade_atual_display', 'quantidade_minima', 'estoque_baixo_display', 'ativo']
    list_filter = ['categoria', 'ativo']
    search_fields = ['nome', 'descricao']
    inlines = [MovimentacaoInline]

    def quantidade_atual_display(self, obj):
        return obj.quantidade_atual
    quantidade_atual_display.short_description = 'Qtd Atual'

    def estoque_baixo_display(self, obj):
        return "⚠️ Baixo" if obj.estoque_baixo else "✅ OK"
    estoque_baixo_display.short_description = 'Status'


@admin.register(Movimentacao)
class MovimentacaoAdmin(ImportExportModelAdmin):
    resource_class = MovimentacaoResource
    formats = [base_formats.XLSX, base_formats.CSV]

    list_display = ['item', 'tipo', 'quantidade', 'registrado_por', 'sabado', 'criado_em']
    list_filter = ['tipo', 'item__categoria', 'sabado', 'criado_em']
    search_fields = ['item__nome', 'observacao']
    autocomplete_fields = ['item']

    def get_export_queryset(self, request):
        queryset = super().get_export_queryset(request)
        cl = self.get_changelist_instance(request)
        return cl.get_queryset(request)

@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "link",
        "quantidade",
        "unidade",
        "valor",
        "valor_total",
        "local",
        "requisitado_por",
        "sabado",
        "area",
    )

    list_filter = (
        "unidade",
        "local__tipo",
        "sabado",
        "area",
    )

    search_fields = (
        "nome",
        "link",
        "local__nome",
        "requisitado_por__username",
    )



    ordering = ("-id",)
    autocomplete_fields = ("local",)
    list_per_page = 20
