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
# registro de origem (reembolso, contribuição de parceiro). Editar/remover pela
# tela do Financeiro deixaria os dois lados divergentes.
#
# 'SUPPLY' saiu daqui quando o espelho automático do Supply foi desligado (ver
# `adm/signals.py`). Nada mais gera esses lançamentos, então não há segundo
# lado para divergir — e mantê-los travados deixaria o ADM sem conseguir
# corrigir nem apagar o que ficou do tempo do espelho.
ORIGENS_AUTOMATICAS = ('REEMBOLSO', 'DOACAO')


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
    # SET_NULL, não CASCADE: estes lançamentos vieram do espelho automático do
    # Supply, que não existe mais, e hoje são registro do ADM. Apagar um pedido
    # antigo lá não pode apagar dinheiro daqui — o Financeiro mudaria sozinho,
    # e o teto da área junto, sem ninguém saber por quê.
    pedido = models.OneToOneField(
        'supply.Pedido', on_delete=models.SET_NULL,
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

    @property
    def e_automatico(self):
        """True quando outro registro do sistema é a fonte da verdade.

        A tela consulta isto em vez de comparar com 'MANUAL': os lançamentos
        de Supply ficaram com `origem='SUPPLY'` mesmo depois de o espelho ser
        desligado, e compará-los com 'MANUAL' os deixaria sem botão de editar
        para sempre.
        """
        return self.origem in ORIGENS_AUTOMATICAS

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
    """Quanto uma área pode gastar por semestre.

    UM teto por área, que vale até alguém alterar ou excluir — não se cadastra
    de novo a cada período. Era mensal antes; virou assim porque na prática o
    valor combinado quase nunca muda, e obrigar a redigitar todo mês fazia a
    tela mentir por esquecimento: sem o teto do mês, a área aparecia como
    "gastou sem teto" mesmo tendo limite combinado.

    O gasto é medido no SEMESTRE corrente. `vigente_desde` é só memória de
    quando o valor passou a valer — não recorta o gasto, porque teto que muda
    no meio do semestre continua sendo o teto daquele semestre.
    """
    area = models.CharField(max_length=30, choices=LISTA_AREAS, unique=True)
    valor = models.DecimalField('teto por semestre', max_digits=10, decimal_places=2)
    vigente_desde = models.DateField('vale a partir de', default=timezone.localdate)
    definido_por = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='tetos_definidos')
    observacao = models.CharField(max_length=200, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['area']
        verbose_name = 'teto de área'
        verbose_name_plural = 'tetos de área'

    def __str__(self):
        return f'{self.get_area_display()} — R$ {self.valor} por semestre'


class RateioDeGasto(models.Model):
    """Quanto cada salinha gastou, SEM que o dinheiro saia de novo.

    O Supply compra com dois ou mais cartões, de voluntários diferentes, numa
    compra só — não separada por salinha. Quem lança o gasto da salinha não tem
    como responder "de qual cartão?", e o extrato não sabe de qual salinha foi.

    Lançar as duas coisas como despesa resolveria o teto e QUEBRARIA O CAIXA:
    os R$800 dos cartões mais os R$800 rateados viram R$1.600 de gasto que não
    existiu.

    **Por isso rateio NÃO é `Lancamento`.** A alternativa era uma marca
    `so_teto` no próprio lançamento, com `.exclude()` nas consultas de total.
    Bastaria UMA consulta futura esquecer o filtro para dinheiro fantasma
    aparecer no caixa — e quem a escrever daqui a um ano não vai saber que a
    marca existe. Como modelo separado isso é impossível por construção: não há
    filtro para esquecer, e o rateio tem um consumidor só, o teto.

    O fluxo: a ADM lança cada cartão com o valor real do extrato (categoria
    "materiais de Supply", ÁREA VAZIA, conta = o cartão) e depois rateia o
    sábado entre as salinhas aqui.
    """
    data = models.DateField(
        'data do gasto', default=timezone.localdate,
        help_text='O sábado. É ela que decide em qual semestre o teto desconta.')
    total_a_ratear = models.DecimalField(
        'total a ratear', max_digits=10, decimal_places=2,
        help_text='Quanto saiu dos cartões neste dia, somando todos.')
    descricao = models.CharField(
        'descrição', max_length=120, blank=True,
        help_text='Distingue dois rateios do mesmo dia. Ex.: materiais, lanches.')
    # NULO SIGNIFICA ABERTO. Sem booleano ao lado: data e booleano são duas
    # verdades sobre o mesmo fato, e na primeira vez que uma for gravada sem a
    # outra ninguem sabe qual vale. Mesmo padrao do `supply.FechamentoSabado`.
    fechado_em = models.DateTimeField('fechado em', null=True, blank=True)
    fechado_por = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL, null=True,
        blank=True, related_name='rateios_fechados')
    criado_por = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL, null=True,
        blank=True, related_name='rateios_criados')
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-data', '-criado_em']
        verbose_name = 'rateio de gasto'
        verbose_name_plural = 'rateios de gasto'

    def __str__(self):
        rotulo = self.descricao or 'Rateio'
        return f'{rotulo} — {self.data:%d/%m/%Y} — R$ {self.total_a_ratear}'

    @property
    def rateado(self):
        """Soma das linhas. Uma consulta."""
        return (self.linhas.aggregate(t=Sum('valor'))['t'] or Decimal('0'))

    @property
    def falta_ratear(self):
        return self.total_a_ratear - self.rateado

    @property
    def esta_aberto(self):
        return self.fechado_em is None

    @property
    def pode_fechar(self):
        """Fechar so vale quando bate no CENTAVO.

        Fechar com sobra transformaria "esqueci metade" em "conferido", que e
        exatamente o que este modelo existe para impedir.
        """
        return self.falta_ratear == Decimal('0')


class LinhaDeRateio(models.Model):
    """Quanto UMA área gastou dentro de um rateio."""
    rateio = models.ForeignKey(
        RateioDeGasto, on_delete=models.CASCADE, related_name='linhas')
    area = models.CharField('área', max_length=30, choices=LISTA_AREAS)
    valor = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['area']
        verbose_name = 'linha de rateio'
        verbose_name_plural = 'linhas de rateio'
        constraints = [
            # Duas linhas "Familia Feliz" no mesmo rateio deixariam a soma
            # ambigua e a tela mostrando a salinha duas vezes.
            models.UniqueConstraint(
                fields=['rateio', 'area'],
                name='uma_linha_por_area_no_rateio',
                violation_error_message=(
                    'Esta área já tem linha neste rateio. Some no valor da '
                    'linha existente em vez de criar outra.'),
            ),
        ]

    def __str__(self):
        return f'{self.get_area_display()} — R$ {self.valor}'
