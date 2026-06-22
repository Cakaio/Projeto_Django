# ronda/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

AREAS_ISENTAS_RONDA = {'TRIADE', 'SUPPLY', 'RECREACAO', 'MARKETING'}

STATUS_CHOICES = (
    ('PENDENTE_SORTEIO', 'Pendente de Sorteio'),
    ('SORTEADA',         'Sorteada — Aguardando Aprovação'),
    ('APROVADA',         'Aprovada'),
    ('REPROVADA',        'Reprovada'),
)


class LocalRonda(models.Model):
    nome  = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordem', 'nome']
        verbose_name = 'Local de Ronda'
        verbose_name_plural = 'Locais de Ronda'

    def __str__(self):
        return self.nome


class ConfiguracaoRondaSabado(models.Model):
    sabado      = models.OneToOneField('sabado.Sabado', on_delete=models.CASCADE, related_name='configuracao_ronda')
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE_SORTEIO')
    criado_por  = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL, null=True, related_name='configuracoes_ronda_criadas')
    criado_em   = models.DateTimeField(default=timezone.now)
    sorteado_em = models.DateTimeField(null=True, blank=True)
    aprovado_por = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL, null=True, blank=True, related_name='rondas_aprovadas')
    aprovado_em  = models.DateTimeField(null=True, blank=True)
    observacao   = models.TextField(blank=True)

    class Meta:
        ordering = ['-sabado__data']
        verbose_name = 'Configuração de Ronda'
        verbose_name_plural = 'Configurações de Ronda'

    def __str__(self):
        return f'Ronda {self.sabado} — {self.get_status_display()}'


class HorarioRonda(models.Model):
    configuracao = models.ForeignKey(ConfiguracaoRondaSabado, on_delete=models.CASCADE, related_name='horarios')
    hora_inicio  = models.TimeField()
    hora_fim     = models.TimeField()
    ordem        = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordem', 'hora_inicio']
        unique_together = ('configuracao', 'hora_inicio', 'hora_fim')
        verbose_name = 'Horário de Ronda'
        verbose_name_plural = 'Horários de Ronda'

    def __str__(self):
        return f'{self.hora_inicio:%H:%M}–{self.hora_fim:%H:%M}'


class EscalaRonda(models.Model):
    horario             = models.ForeignKey(HorarioRonda, on_delete=models.CASCADE, related_name='escalas')
    local               = models.ForeignKey(LocalRonda, on_delete=models.PROTECT, related_name='escalas')
    voluntario          = models.ForeignKey('voluntario.Voluntario', on_delete=models.CASCADE, related_name='escalas_ronda')
    is_substituto       = models.BooleanField(default=False)
    voluntario_original = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL, null=True, blank=True, related_name='escalas_substituidas')
    criado_em           = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('horario', 'local', 'voluntario')
        verbose_name = 'Escala de Ronda'
        verbose_name_plural = 'Escalas de Ronda'

    def clean(self):
        count = EscalaRonda.objects.filter(horario=self.horario, local=self.local).exclude(pk=self.pk).count()
        if count >= 2:
            raise ValidationError('Máximo de 2 voluntários por local e horário.')

    def __str__(self):
        return f'{self.voluntario} — {self.local} — {self.horario}'


class ScoreRonda(models.Model):
    voluntario = models.ForeignKey('voluntario.Voluntario', on_delete=models.CASCADE, related_name='scores_ronda')
    ano    = models.PositiveSmallIntegerField()
    pontos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ('voluntario', 'ano')
        ordering = ['-pontos']
        verbose_name = 'Score de Ronda'
        verbose_name_plural = 'Scores de Ronda'

    def __str__(self):
        return f'{self.voluntario} — {self.ano}: {self.pontos} pt(s)'

    @classmethod
    def incrementar(cls, voluntario, ano):
        obj, _ = cls.objects.get_or_create(voluntario=voluntario, ano=ano)
        cls.objects.filter(pk=obj.pk).update(pontos=models.F('pontos') + 1)
