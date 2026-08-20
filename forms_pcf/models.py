from django.db import models
from django.utils import timezone
from voluntario.models import LISTA_AREAS

STATUS_CHOICES = (
    ('PENDENTE', 'Pendente'),
    ('APROVADO', 'Aprovado'),
    # PAGO vem depois de APROVADO porque é o passo seguinte, não um substituto:
    # aprovado é a decisão, pago é o dinheiro tendo saído de verdade.
    ('PAGO', 'Pago'),
    ('REJEITADO', 'Rejeitado'),
)


class FeedbackArea(models.Model):
    area = models.CharField(max_length=30, choices=LISTA_AREAS)
    descricao = models.TextField(blank=True, null=True, help_text="Dores da sua área")
    dor_geral = models.TextField(blank=True, null=True, help_text="Dores do PCF em geral")
    sugestao = models.TextField(blank=True, null=True, help_text="Sugestões de projetos")
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Feedback de Área'
        verbose_name_plural = 'Feedbacks de Área'

    def __str__(self):
        return f'{self.area} — {self.criado_em:%d/%m/%Y}'


class PedidoReembolso(models.Model):
    solicitante = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL,
        null=True, related_name='pedidos_reembolso'
    )
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    descricao = models.TextField()
    data_gasto = models.DateField()
    categoria = models.ForeignKey(
        'adm.Categoria', on_delete=models.PROTECT, related_name='pedidos_reembolso'
    )
    # O comprovante do gasto, enviado pelo voluntário. Nada a ver com
    # `comprovante_pagamento`, que é o do ADM: reaproveitar um campo para os
    # dois apagaria a prova de um dos lados.
    comprovante = models.FileField(upload_to='reembolsos/')
    area = models.CharField('área', max_length=30, choices=LISTA_AREAS, blank=True)
    evento = models.ForeignKey('adm.Evento', on_delete=models.SET_NULL, null=True,
                               blank=True, related_name='reembolsos')
    conta_pagamento = models.ForeignKey('adm.Conta', on_delete=models.SET_NULL, null=True,
                                        blank=True, related_name='reembolsos_pagos',
                                        help_text='De onde saiu o pagamento.')
    comprovante_pagamento = models.FileField(upload_to='reembolsos_pagos/', blank=True,
                                             help_text='Comprovante de que o ADM pagou.')
    pago_em = models.DateField(null=True, blank=True)
    pago_por = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name='reembolsos_pagos_por')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDENTE')
    observacao_adm = models.TextField(blank=True)
    aprovado_por = models.ForeignKey(
        'voluntario.Voluntario', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reembolsos_aprovados'
    )
    aprovado_em = models.DateTimeField(null=True, blank=True)
    lancamento = models.OneToOneField(
        'adm.Lancamento', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='pedido_reembolso'
    )
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Pedido de Reembolso'
        verbose_name_plural = 'Pedidos de Reembolso'

    def __str__(self):
        return f'Reembolso R$ {self.valor} — {self.status}'


class ReceptorNotificacaoReembolso(models.Model):
    nome = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Receptor de Notificação'
        verbose_name_plural = 'Receptores de Notificação'

    def __str__(self):
        return f'{self.nome} <{self.email}>'
