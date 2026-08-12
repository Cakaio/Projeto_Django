"""Editais e chamadas públicas (área CR/RE).

O robô (`coleta.py` + `manage.py buscar_editais`) varre as fontes cadastradas e
guarda aqui o que tem cara de servir ao PCF. Fontes, seletores e palavras-chave
moram no banco porque quem entende de captação é o CR, não o código — e site de
edital muda de layout sem avisar.
"""
import hashlib
from django.db import models
from django.utils import timezone

TIPO_FONTE = (('RSS', 'RSS / Atom'), ('HTML', 'Página HTML'))
STATUS_EDITAL = (
    ('NOVO', 'Novo'),
    ('AVALIANDO', 'Avaliando'),
    ('VAMOS_CONCORRER', 'Vamos concorrer'),
    ('INSCRITO', 'Inscrito'),
    ('DESCARTADO', 'Descartado'),
    ('ENCERRADO', 'Encerrado'),
)


class FonteEdital(models.Model):
    """De onde o robô lê. Os seletores ficam no banco de propósito: site de
    edital muda de layout sem avisar, e assim dá para consertar pela tela sem
    mexer em código nem fazer deploy."""
    nome = models.CharField(max_length=120)
    url = models.URLField(max_length=500)
    tipo = models.CharField(max_length=6, choices=TIPO_FONTE, default='RSS')
    seletor_item = models.CharField('seletor do item', max_length=200, blank=True,
                                    help_text='CSS de cada edital na página. Só para fonte HTML.')
    seletor_titulo = models.CharField('seletor do título', max_length=200, blank=True)
    seletor_link = models.CharField('seletor do link', max_length=200, blank=True)
    seletor_descricao = models.CharField('seletor da descrição', max_length=200, blank=True)
    ativo = models.BooleanField(default=True)
    ultima_coleta = models.DateTimeField(null=True, blank=True)
    ultimo_erro = models.TextField(blank=True)
    itens_ultima_coleta = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['nome']
        verbose_name = 'fonte de editais'
        verbose_name_plural = 'fontes de editais'

    def __str__(self):
        return self.nome

    @property
    def saudavel(self):
        return self.ativo and not self.ultimo_erro


class PalavraChave(models.Model):
    """Peso positivo aproxima o edital do PCF; negativo afasta. Editável pela
    tela porque quem sabe o que serve para o projeto é o CR, não o código."""
    termo = models.CharField(max_length=80, unique=True)
    peso = models.IntegerField(default=1, help_text='Positivo atrai, negativo descarta.')
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['-peso', 'termo']
        verbose_name = 'palavra-chave'
        verbose_name_plural = 'palavras-chave'

    def __str__(self):
        return f'{self.termo} ({self.peso:+d})'


class ConsultaBusca(models.Model):
    """Uma pergunta que o robô faz ao buscador.

    Ler fontes cadastradas só acha edital em lugar que alguém já conhecia — e o
    PCF não conhecia nenhum. É esta varredura que descobre o que ninguém sabia
    que existia: o robô pergunta à web, colhe o que voltar de qualquer site e
    pontua igual ao resto. Quando um domínio aparece sempre, vale promovê-lo a
    FonteEdital e passar a ler todo dia.
    """
    termo = models.CharField('o que perguntar', max_length=200, unique=True)
    ativo = models.BooleanField(default=True)
    ultima_busca = models.DateTimeField(null=True, blank=True)
    resultados_ultima_busca = models.PositiveIntegerField(default=0)
    ultimo_erro = models.TextField(blank=True)

    class Meta:
        ordering = ['termo']
        verbose_name = 'consulta de busca'
        verbose_name_plural = 'consultas de busca'

    def __str__(self):
        return self.termo

    @property
    def saudavel(self):
        return self.ativo and not self.ultimo_erro


class Edital(models.Model):
    titulo = models.CharField('título', max_length=250)
    descricao = models.TextField('descrição', blank=True)
    requisitos = models.TextField('o que precisamos', blank=True)
    link = models.URLField(max_length=500)
    fonte = models.ForeignKey(FonteEdital, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='editais')
    consulta = models.ForeignKey(ConsultaBusca, on_delete=models.SET_NULL, null=True,
                                 blank=True, related_name='editais',
                                 help_text='Qual pergunta trouxe este edital, quando veio da varredura.')
    origem = models.CharField(max_length=6, default='ROBO',
                              choices=(('ROBO', 'Fonte fixa'),
                                       ('BUSCA', 'Varredura na web'),
                                       ('MANUAL', 'Cadastro manual')))
    prazo = models.DateField('prazo de inscrição', null=True, blank=True)
    valor = models.DecimalField('valor previsto', max_digits=12, decimal_places=2,
                                null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_EDITAL, default='NOVO')
    relevancia = models.IntegerField(default=0)
    termos_encontrados = models.CharField(max_length=250, blank=True)
    responsavel = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='editais')
    observacoes = models.TextField('observações', blank=True)
    chave = models.CharField(max_length=64, unique=True, db_index=True)
    criado_em = models.DateTimeField(default=timezone.now)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-relevancia', 'prazo', '-criado_em']
        verbose_name = 'edital'
        verbose_name_plural = 'editais'

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        if not self.chave:
            # Dedupe pelo link: a mesma chamada aparece em vários lugares e o
            # robô roda todo dia — sem isso a lista viraria repetição.
            self.chave = hashlib.sha256(self.link.strip().lower().encode()).hexdigest()
        super().save(*args, **kwargs)

    @property
    def dominio(self):
        """Só o site, sem 'www' nem o caminho. Para o edital achado na varredura
        é a informação mais útil da linha: é o site que pode virar fonte fixa."""
        from .busca import dominio_de
        return dominio_de(self.link)

    @property
    def prazo_proximo(self):
        """True se falta uma semana ou menos — a tela destaca isso."""
        if not self.prazo:
            return False
        return 0 <= (self.prazo - timezone.localdate()).days <= 7

    @property
    def vencido(self):
        return bool(self.prazo) and self.prazo < timezone.localdate()
