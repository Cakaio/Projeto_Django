"""CRM de Parceiros (área CR/RE).

Substitui a planilha "Parceiros Felizes": cada parceiro tem um voluntário do
CR responsável (a "carteira") e contribuições registradas mês a mês. Meses sem
doação simplesmente não têm registro — doação é voluntária e pode faltar.

Cada contribuição vira um lançamento de RECEITA no Financeiro (origem DOACAO),
para aparecer sozinha no fluxo de caixa e no DRE. Ver `signals.py`.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.utils import timezone

STATUS_PARCEIRO = (
    ('PROSPECTO', 'Prospecto'),      # em conversa, ainda não doou
    ('ATIVO', 'Ativo'),
    ('PAUSADO', 'Pausado'),          # parou por ora, mas a relação segue
    ('ENCERRADO', 'Encerrado'),
)

FORMAS_CONTRIBUICAO = (
    ('PIX', 'Pix'),
    ('TRANSFERENCIA', 'Transferência'),
    ('DINHEIRO', 'Dinheiro'),
    ('BOLETO', 'Boleto'),
    ('OUTRO', 'Outro'),
)

TIPOS_INTERACAO = (
    ('CONTATO', 'Contato'),
    ('AGRADECIMENTO', 'Agradecimento'),
    ('COBRANCA', 'Lembrete de doação'),
    ('REUNIAO', 'Reunião'),
    ('OBSERVACAO', 'Observação'),
)

# Categoria de receita usada pelos lançamentos gerados a partir do CRM.
CATEGORIA_DOACOES = 'Doações de Parceiros'


class Parceiro(models.Model):
    """Pessoa ou empresa que doa para o projeto."""

    nome = models.CharField(
        max_length=150,
        help_text='Nome completo, exatamente como deve sair no recibo/nota.',
    )
    responsavel = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='parceiros',
        help_text='Voluntário do CR que cuida dessa relação (a carteira).',
    )
    status = models.CharField(max_length=12, choices=STATUS_PARCEIRO, default='ATIVO')

    email = models.EmailField(blank=True)
    telefone = models.CharField('telefone / WhatsApp', max_length=20, blank=True)
    documento = models.CharField(
        'CPF / CNPJ', max_length=20, blank=True,
        help_text='Opcional. Necessário apenas se for emitir recibo.',
    )
    valor_referencia = models.DecimalField(
        'valor de referência', max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Quanto costuma doar por mês. Só orientativo — não gera cobrança.',
    )
    observacoes = models.TextField('observações', blank=True)

    criado_em = models.DateTimeField(default=timezone.now)
    criado_por = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='parceiros_cadastrados',
    )

    class Meta:
        ordering = ['nome']
        verbose_name = 'Parceiro'
        verbose_name_plural = 'Parceiros'

    def __str__(self):
        return self.nome

    @property
    def total_arrecadado(self):
        return self.contribuicoes.aggregate(t=Sum('valor'))['t'] or Decimal('0')

    def total_no_ano(self, ano):
        return self.contribuicoes.filter(competencia__year=ano).aggregate(
            t=Sum('valor'))['t'] or Decimal('0')

    @property
    def ultima_contribuicao(self):
        return self.contribuicoes.order_by('-competencia').first()


class Contribuicao(models.Model):
    """Uma doação recebida de um parceiro, referente a um mês (competência)."""

    parceiro = models.ForeignKey(
        Parceiro, on_delete=models.CASCADE, related_name='contribuicoes',
    )
    competencia = models.DateField(
        'mês de referência',
        help_text='Mês a que a doação se refere. O dia é normalizado para 1.',
    )
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data_recebimento = models.DateField(
        help_text='Data em que o dinheiro entrou. É ela que vale no fluxo de caixa e no DRE.',
    )
    forma = models.CharField(max_length=15, choices=FORMAS_CONTRIBUICAO, default='PIX', blank=True)
    # Qual banco recebeu. Opcional porque o histórico já lançado não registrou
    # isso, e exigir agora travaria a edição de contribuição antiga.
    conta = models.ForeignKey(
        'adm.Conta', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='contribuicoes',
        help_text='Onde o dinheiro caiu (ex.: BB, Caju).',
    )
    observacao = models.CharField('observação', max_length=200, blank=True)

    # Lançamento gerado no Financeiro. SET_NULL para que apagar um lançamento
    # à mão (via admin) não apague a contribuição.
    lancamento = models.OneToOneField(
        'adm.Lancamento', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contribuicao',
    )

    registrado_por = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contribuicoes_registradas',
    )
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-competencia', 'parceiro__nome']
        verbose_name = 'Contribuição'
        verbose_name_plural = 'Contribuições'
        constraints = [
            models.UniqueConstraint(
                fields=['parceiro', 'competencia'],
                name='parceiro_uma_contribuicao_por_mes',
            ),
        ]

    def __str__(self):
        return f'{self.parceiro} — {self.competencia:%m/%Y} — R$ {self.valor}'

    def save(self, *args, **kwargs):
        # Competência é sempre o primeiro dia do mês, para agrupar sem ambiguidade.
        if self.competencia:
            self.competencia = self.competencia.replace(day=1)
        if not self.data_recebimento:
            self.data_recebimento = self.competencia
        super().save(*args, **kwargs)


class Interacao(models.Model):
    """Histórico de relacionamento — o que a planilha não guardava."""

    parceiro = models.ForeignKey(
        Parceiro, on_delete=models.CASCADE, related_name='interacoes',
    )
    data = models.DateField(default=timezone.localdate)
    tipo = models.CharField(max_length=15, choices=TIPOS_INTERACAO, default='CONTATO')
    descricao = models.TextField('descrição')
    autor = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='interacoes_parceiros',
    )
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-data', '-criado_em']
        verbose_name = 'Interação'
        verbose_name_plural = 'Interações'

    def __str__(self):
        return f'{self.parceiro} — {self.get_tipo_display()} em {self.data:%d/%m/%Y}'
