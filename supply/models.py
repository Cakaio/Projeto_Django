from django.db import models
from django.utils import timezone

CATEGORIAS = (
    ("PAPELARIA", "Papelaria"),
    ("LIMPEZA", "Limpeza"),
    ("ALIMENTACAO", "Alimentação"),
    ("ESCRITORIO", "Escritório"),
    ("ESPORTES", "Esportes"),
    ("ARTESANATO", "Artesanato"),
    ("HIGIENE", "Higiene"),
    ("OUTROS", "Outros"),
)

UNIDADES = (
    ("UN", "Unidade"),
    ("PAC", "Pacote"),
    ("CX", "Caixa"),
    ("TUBO", "Tubo"),
    ("METRO", "Metro"),
    ("L", "Litro"),
    ("KG", "Quilo"),
    ("FOLHA", "Folha"),
    ("ROLO", "Rolo"),
    ("OUTROS", "Outros"),
)

TIPO_MOVIMENTACAO = (
    ("ENTRADA", "Entrada"),
    ("SAIDA", "Saída"),
    ("AJUSTE", "Ajuste de Inventário"),
)


class Item(models.Model):
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True, null=True)
    categoria = models.CharField(max_length=50, choices=CATEGORIAS, default="OUTROS")
    unidade = models.CharField(max_length=20, choices=UNIDADES, default="UN")
    quantidade_minima = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Quantidade mínima para alerta de estoque baixo"
    )
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']
        verbose_name = "Item"
        verbose_name_plural = "Itens"

    def __str__(self):
        return f"{self.nome} ({self.get_unidade_display()})"

    @property
    def quantidade_atual(self):
        from django.db.models import Sum
        entradas = self.movimentacoes.filter(
            tipo="ENTRADA"
        ).aggregate(total=Sum('quantidade'))['total'] or 0
        saidas = self.movimentacoes.filter(
            tipo="SAIDA"
        ).aggregate(total=Sum('quantidade'))['total'] or 0
        ajustes = self.movimentacoes.filter(
            tipo="AJUSTE"
        ).aggregate(total=Sum('quantidade'))['total'] or 0
        return entradas - saidas + ajustes

    @property
    def estoque_baixo(self):
        return self.quantidade_atual <= self.quantidade_minima


class Movimentacao(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="movimentacoes")
    tipo = models.CharField(max_length=20, choices=TIPO_MOVIMENTACAO)
    quantidade = models.DecimalField(max_digits=10, decimal_places=2)
    observacao = models.TextField(blank=True, null=True)
    registrado_por = models.ForeignKey(
        "voluntario.Voluntario",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="movimentacoes_supply"
    )
    sabado = models.ForeignKey(
        "sabado.Sabado",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="movimentacoes_supply",
        help_text="Sábado relacionado à movimentação (opcional)"
    )
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = "Movimentação"
        verbose_name_plural = "Movimentações"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.item.nome}: {self.quantidade}"
