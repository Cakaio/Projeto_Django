from django.db import models
from django.utils import timezone

from voluntario.views import LISTA_AREAS

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

TIPOS_LOCAL = (
    ("MERCADO", "Mercado"),
    ("SUPERMERCADO", "Supermercado"),
    ("PAPELARIA", "Papelaria"),
    ("ARTIGOS_FESTA", "Artigos de festa"),
    ("ATACADISTA", "Atacadista"),
    ("LOJA_UTILIDADES", "Loja de utilidades"),
    ("ONLINE", "Loja online"),
    ("OUTROS", "Outros"),
)


class Local(models.Model):
    nome = models.CharField(max_length=150)
    tipo = models.CharField(max_length=30, choices=TIPOS_LOCAL, default="OUTROS")
    localizacao = models.CharField("endereço/localização", max_length=255, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    numero_contato = models.CharField("número de contato", max_length=30, blank=True)
    whatsapp = models.BooleanField("contato possui WhatsApp", default=False)
    email = models.EmailField(blank=True)
    site = models.URLField(blank=True)
    observacoes = models.TextField(blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nome",)
        verbose_name = "Local de compra"
        verbose_name_plural = "Locais de compra"
        constraints = [
            models.UniqueConstraint(fields=("nome", "tipo"), name="local_nome_tipo_unicos")
        ]

    def __str__(self):
        return f"{self.nome} — {self.get_tipo_display()}"


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


class Pedido(models.Model):
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="pedidos")
    nome = models.CharField(max_length=100)
    especificar = models.TextField(blank=True)
    link = models.URLField("link da imagem", blank=True)
    quantidade = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    unidade = models.CharField(max_length=10, choices=UNIDADES, default="UN")
    valor = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    local = models.ForeignKey(Local, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos")
    requisitado_por = models.ForeignKey("voluntario.Voluntario",on_delete=models.SET_NULL,null=True, blank=True,related_name="pedidos_requisitados")
    sabado = models.ForeignKey("sabado.Sabado",on_delete=models.SET_NULL,null=True, blank=True,related_name="pedidos_do_sabado",help_text="Sábado relacionado ao pedido")
    area = models.CharField(max_length=30, choices=LISTA_AREAS, null=True, blank=True)

    @property
    def valor_total(self):
        """Retorna o custo total do pedido (valor unitário x quantidade)."""
        if self.valor is None:
            return None
        return self.valor * self.quantidade

    def __str__(self):
        return f"{self.nome}"

    def save(self, *args, **kwargs):
        if self.item_id:
            self.nome = self.item.nome
            self.unidade = self.item.unidade
        super().save(*args, **kwargs)
