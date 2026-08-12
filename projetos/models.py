"""Backlog da área de Projetos.

Projetos implementa funcionalidades do site POR ÁREA do PCF, e até aqui nada
disso ficava registrado: com quem conversaram, o que já foi entregue, se a área
respondeu ou sumiu. Duas coisas moram neste app — a demanda (o item do backlog)
e o histórico dela (o que aconteceu, linha por linha).
"""
from django.db import models
from django.urls import reverse
from django.utils import timezone

from voluntario.models import LISTA_AREAS

STATUS_DEMANDA = (
    ('IDEIA', 'Ideia'),
    ('CONVERSANDO', 'Conversando com a área'),
    ('ESPERANDO_AREA', 'Esperando a área'),
    ('FAZENDO', 'Fazendo'),
    ('ENTREGUE', 'Entregue'),
    ('PAUSADO', 'Pausado'),
    ('DESCARTADO', 'Descartado'),
)

# Estes três são o que interessa quando se pergunta "o que está em pé?".
STATUS_ABERTOS = ('IDEIA', 'CONVERSANDO', 'ESPERANDO_AREA', 'FAZENDO')

RETORNO_AREA = (
    ('SEM_CONTATO', 'Ainda não procuramos'),
    ('AGUARDANDO', 'Procuramos, aguardando resposta'),
    ('RESPONDEU', 'Respondeu'),
    ('NAO_RESPONDE', 'Não respondeu'),
)

PRIORIDADES = (('ALTA', 'Alta'), ('MEDIA', 'Média'), ('BAIXA', 'Baixa'))

TIPOS_REGISTRO = (
    ('CONVERSA', 'Conversa com a área'),
    ('COBRANCA', 'Cobrança'),
    ('RETORNO', 'Retorno da área'),
    ('ENTREGA', 'Entrega no site'),
    ('NOTA', 'Anotação'),
)


class Demanda(models.Model):
    """Um item do backlog: algo que Projetos está fazendo (ou pensando em
    fazer) para uma área do PCF."""
    titulo = models.CharField('título', max_length=160)
    area = models.CharField('área atendida', max_length=30, choices=LISTA_AREAS,
                            help_text='Para qual área do projeto é esta demanda.')
    o_que_pediram = models.TextField('o que a área pediu', blank=True)
    o_que_fizemos = models.TextField('o que já fizemos no site', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_DEMANDA, default='IDEIA')
    retorno = models.CharField('retorno da área', max_length=20,
                               choices=RETORNO_AREA, default='SEM_CONTATO')
    prioridade = models.CharField(max_length=10, choices=PRIORIDADES, default='MEDIA')
    responsavel = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='demandas')
    contato_na_area = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='demandas_como_contato',
                                        help_text='Com quem falamos nessa área.')
    entregue_em = models.DateField('entregue em', null=True, blank=True)
    criado_por = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='demandas_criadas')
    criado_em = models.DateTimeField(default=timezone.now)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-atualizado_em']
        verbose_name = 'demanda'
        verbose_name_plural = 'demandas'

    def __str__(self):
        return f'{self.titulo} ({self.get_area_display()})'

    def get_absolute_url(self):
        return reverse('projetos:ficha', args=[self.pk])

    @property
    def aberta(self):
        return self.status in STATUS_ABERTOS

    @property
    def dias_parada(self):
        """Dias desde o último registro (ou desde a criação, se não houver).

        É o número que denuncia o que está no vácuo — a dor que originou esta
        tela. Só faz sentido para demanda aberta.
        """
        hoje = timezone.localdate()
        # Ignora registro com data futura. `data` é digitada à mão, e um erro de
        # digitação (2027 no lugar de 2026) daria "parada há -300 dias": a
        # demanda sumiria da lista de travadas e do topo do panorama, que são
        # exatamente os lugares onde ela precisa aparecer.
        ultimo = self.registros.filter(data__lte=hoje).order_by('-data').first()
        referencia = ultimo.data if ultimo else timezone.localdate(self.criado_em)
        return (hoje - referencia).days

    @property
    def travada(self):
        """Aberta, esperando a área e parada há mais de 14 dias."""
        return (self.aberta
                and self.retorno in ('AGUARDANDO', 'NAO_RESPONDE')
                and self.dias_parada > 14)


class RegistroDemanda(models.Model):
    """Uma linha do histórico. É o que responde "o que aconteceu com isso?"
    meses depois, quando ninguém lembra mais."""
    demanda = models.ForeignKey(Demanda, on_delete=models.CASCADE, related_name='registros')
    data = models.DateField(default=timezone.localdate)
    tipo = models.CharField(max_length=20, choices=TIPOS_REGISTRO, default='NOTA')
    descricao = models.TextField('o que aconteceu')
    autor = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                              null=True, blank=True, related_name='registros_demanda')
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-data', '-criado_em']
        verbose_name = 'registro'
        verbose_name_plural = 'registros'

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.data:%d/%m/%Y}'
