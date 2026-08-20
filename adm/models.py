from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.utils import timezone

from voluntario.models import LISTA_AREAS

TIPO_CHOICES = (
    ('RECEITA', 'Receita'),
    ('DESPESA', 'Despesa'),
)

ORIGEM_CHOICES = (
    ('MANUAL', 'Manual'),
    ('SUPPLY', 'Supply'),
    ('REEMBOLSO', 'Reembolso'),
    ('DOACAO', 'Doação'),
)

# Lançamentos gerados por outra área do sistema: a fonte da verdade é o
# registro de origem (pedido do Supply, reembolso, contribuição de parceiro).
# Editar/remover pela tela do Financeiro deixaria os dois lados divergentes.
ORIGENS_AUTOMATICAS = ('SUPPLY', 'REEMBOLSO', 'DOACAO')


class Categoria(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['tipo', 'nome']
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'

    def __str__(self):
        return f'{self.nome} ({self.get_tipo_display()})'


class Lancamento(models.Model):
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, editable=False)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name='lancamentos'
    )
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateField()
    descricao = models.TextField(blank=True)
    origem = models.CharField(max_length=10, choices=ORIGEM_CHOICES, default='MANUAL')
    pedido = models.OneToOneField(
        'supply.Pedido', on_delete=models.CASCADE,
        null=True, blank=True, related_name='lancamento'
    )
    # Os três campos abaixo são opcionais porque o histórico já gravado não tem
    # essa informação: exigir preenchimento impediria de salvar o que já existe.
    conta = models.ForeignKey(
        'Conta', on_delete=models.PROTECT, null=True, blank=True,
        related_name='lancamentos',
        help_text='Banco, cartão ou dinheiro físico.'
    )
    area = models.CharField(
        'área', max_length=30, choices=LISTA_AREAS, blank=True,
        help_text='Para qual área do projeto foi este gasto.'
    )
    evento = models.ForeignKey(
        'Evento', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lancamentos'
    )
    criado_por = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='lancamentos_criados'
    )
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-data', '-criado_em']
        verbose_name = 'Lançamento'
        verbose_name_plural = 'Lançamentos'

    def save(self, *args, **kwargs):
        self.tipo = self.categoria.tipo
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_tipo_display()} — R$ {self.valor} ({self.data})'


TIPOS_CONTA = (
    ('BANCO', 'Banco'),
    ('CARTAO', 'Cartão'),
    ('DINHEIRO', 'Dinheiro físico'),
)


class Conta(models.Model):
    """De onde o dinheiro saiu ou para onde entrou.

    Cadastrável pela tela de propósito: hoje são BB, Mercado Pago, Caju e
    dinheiro físico, mas conta nova aparece sem aviso e ninguém deveria
    precisar de deploy para registrar uma.
    """
    nome = models.CharField(max_length=60, unique=True)
    tipo = models.CharField(max_length=10, choices=TIPOS_CONTA, default='BANCO')
    controla_saldo = models.BooleanField(
        'controlar saldo desta conta', default=False,
        help_text='Ligue para cartão pré-pago: o saldo é recarga menos gasto. '
                  'Deixe desligado para conta de banco, onde o extrato manda.')
    responsavel = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='contas_sob_responsabilidade',
        help_text='Com quem está o cartão hoje.')
    ativo = models.BooleanField(default=True)
    observacao = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['tipo', 'nome']
        verbose_name = 'conta'
        verbose_name_plural = 'contas'

    def __str__(self):
        return self.nome

    # As quatro propriedades abaixo devolvem Decimal('0') quando não há
    # registro: a tela formata como dinheiro e `None` viraria "R$ None".
    @property
    def total_recarregado(self):
        return self.recargas.aggregate(t=Sum('valor'))['t'] or Decimal('0')

    @property
    def total_gasto(self):
        """Só DESPESA: receita que entrou nesta conta não consome o saldo."""
        return (self.lancamentos.filter(tipo='DESPESA')
                .aggregate(t=Sum('valor'))['t'] or Decimal('0'))

    @property
    def saldo(self):
        return self.total_recarregado - self.total_gasto

    @property
    def saldo_negativo(self):
        """Saldo negativo é sinal de recarga não registrada, não de erro de
        conta: quem olha a tela precisa ver o vermelho para ir atrás."""
        return self.saldo < 0


class RecargaCartao(models.Model):
    """Uma recarga de cartão. É a entrada que forma o saldo.

    NÃO gera Lancamento: recarregar cartão é mover dinheiro de uma conta para
    outra, não gastar. Lançar como despesa contaria o mesmo real duas vezes —
    uma na recarga, outra quando o cartão for usado.
    """
    conta = models.ForeignKey(Conta, on_delete=models.CASCADE, related_name='recargas')
    data = models.DateField(default=timezone.localdate)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    area = models.CharField('para qual área foi', max_length=30,
                            choices=LISTA_AREAS, blank=True)
    carregado_por = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='recargas_feitas')
    motivo = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-data', '-criado_em']
        verbose_name = 'recarga de cartão'
        verbose_name_plural = 'recargas de cartão'

    def __str__(self):
        return f'{self.conta} — R$ {self.valor} ({self.data:%d/%m/%Y})'


class Evento(models.Model):
    """Ex.: PC Feijuca. Entra mínimo: o painel completo (arrecadado, lucro)
    fica para depois; aqui ele existe para o gasto poder ser atribuído."""
    nome = models.CharField(max_length=80, unique=True)
    data = models.DateField(null=True, blank=True)
    teto = models.DecimalField('teto de gasto', max_digits=10, decimal_places=2,
                               null=True, blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['-data', 'nome']

    def __str__(self):
        return self.nome


class TetoArea(models.Model):
    """Quanto uma área pode gastar num mês.

    `competencia` é sempre o dia 1 do mês (normalizado no save), igual ao que
    `parceiros.Contribuicao` faz: guardar o dia real deixaria dois tetos do
    mesmo mês conviverem e ninguém saberia qual vale.
    """
    area = models.CharField(max_length=30, choices=LISTA_AREAS)
    competencia = models.DateField('mês de referência')
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    definido_por = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='tetos_definidos')
    observacao = models.CharField(max_length=200, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-competencia', 'area']
        constraints = [models.UniqueConstraint(fields=['area', 'competencia'],
                                               name='um_teto_por_area_por_mes')]
        verbose_name = 'teto de área'
        verbose_name_plural = 'tetos de área'

    def __str__(self):
        return f'{self.get_area_display()} — {self.competencia:%m/%Y} — R$ {self.valor}'

    def save(self, *args, **kwargs):
        # Dia 1 sempre: dois tetos do mesmo mês com dias diferentes passariam
        # pela constraint e ninguém saberia qual vale.
        if self.competencia:
            self.competencia = self.competencia.replace(day=1)
        super().save(*args, **kwargs)
