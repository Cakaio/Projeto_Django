from django.db import models
from django.utils import timezone

from voluntario.views import LISTA_AREAS

CATEGORIAS = (
    ("PAPELARIA", "Papelaria"),
    ("LIMPEZA", "Limpeza"),
    ("ALIMENTACAO", "Alimentação"),
    ("ESPORTES", "Esportes"),
    ("ARTESANATO", "Artesanato"),
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
        return f"{self.nome}"


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
        super().save(*args, **kwargs)


class FechamentoSabado(models.Model):
    """Quem já atualizou os gastos reais daquele sábado, e quando.

    Depois do sábado o Supply volta e corrige o que foi de fato usado e
    comprado. Até existir este registro a ADM não tinha como saber se os
    números da tela já eram os reais ou ainda os do planejamento — e perguntava
    no grupo toda semana.

    **Não há campo booleano: a DATA preenchida É o check.** Booleano mais data
    são duas verdades sobre o mesmo fato; na primeira vez que uma for gravada
    sem a outra, ninguém mais sabe qual vale.

    Duas etapas separadas porque são dois trabalhos diferentes, feitos às vezes
    por pessoas diferentes: conferir o que saiu do estoque (materiais) e
    conferir o que foi comprado (pedidos). Um check só diria "está fechado" sem
    dizer o que ainda falta, que é justamente a informação acionável.
    """

    MATERIAIS = 'materiais'
    PEDIDOS = 'pedidos'
    ETAPAS = (MATERIAIS, PEDIDOS)

    sabado = models.OneToOneField(
        'sabado.Sabado', on_delete=models.CASCADE, related_name='fechamento_supply'
    )
    materiais_conferidos_por = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fechamentos_de_material'
    )
    materiais_conferidos_em = models.DateTimeField(null=True, blank=True)
    pedidos_conferidos_por = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fechamentos_de_pedido'
    )
    pedidos_conferidos_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'fechamento do sábado'
        verbose_name_plural = 'fechamentos do sábado'

    def __str__(self):
        return f'Fechamento do Supply — {self.sabado}'

    @classmethod
    def do_sabado(cls, sabado):
        """O fechamento daquele sábado, criando na hora se ainda não existir.

        A tela não pode exigir que alguém cadastre o fechamento antes de poder
        marcar: o registro nasce da primeira visita, não de um cadastro.
        """
        fechamento, _ = cls.objects.get_or_create(sabado=sabado)
        return fechamento

    @property
    def materiais_conferidos(self):
        return self.materiais_conferidos_em is not None

    @property
    def pedidos_conferidos(self):
        return self.pedidos_conferidos_em is not None

    @property
    def completo(self):
        return self.materiais_conferidos and self.pedidos_conferidos

    @property
    def pendentes(self):
        """As etapas que ainda faltam, com o rótulo que a tela mostra."""
        faltando = []
        if not self.materiais_conferidos:
            faltando.append('materiais')
        if not self.pedidos_conferidos:
            faltando.append('pedidos')
        return faltando

    def _campos(self, etapa):
        if etapa not in self.ETAPAS:
            raise ValueError(f'Etapa desconhecida: {etapa!r}')
        return f'{etapa}_conferidos_por', f'{etapa}_conferidos_em'

    def marcar(self, etapa, voluntario):
        """Registra a conferência. Remarcar troca o nome e a hora.

        Quem confere de novo passa a ser o responsável: a informação útil é
        quem garantiu por último, não quem garantiu primeiro.
        """
        campo_por, campo_em = self._campos(etapa)
        setattr(self, campo_por, voluntario)
        setattr(self, campo_em, timezone.now())
        self.save(update_fields=[campo_por, campo_em])

    def desmarcar(self, etapa):
        """Volta a etapa para pendente, limpando os DOIS campos.

        Nome sem data seria meia verdade: a tela diria "conferido" sem saber
        por quando, e a ADM não teria como julgar se o número é recente.
        """
        campo_por, campo_em = self._campos(etapa)
        setattr(self, campo_por, None)
        setattr(self, campo_em, None)
        self.save(update_fields=[campo_por, campo_em])
