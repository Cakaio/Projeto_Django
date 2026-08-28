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
    pessoas_por_grupo = models.PositiveSmallIntegerField(
        default=2,
        verbose_name='Pessoas por grupo',
        help_text='Tamanho de cada grupo do rodízio (2 = duplas, 3 = trios). '
                  'Em dia de evento o local recebe 2 grupos desse tamanho.',
    )

    class Meta:
        ordering = ['ordem', 'nome']
        verbose_name = 'Local de Ronda'
        verbose_name_plural = 'Locais de Ronda'

    def __str__(self):
        return self.nome

    @property
    def rotulo_grupo(self):
        return {2: 'Dupla', 3: 'Trio', 4: 'Quarteto'}.get(self.pessoas_por_grupo, 'Grupo')

    @property
    def total_evento(self):
        """Pessoas necessárias no local em dia de evento (2 grupos fixos)."""
        return (self.pessoas_por_grupo or 2) * 2


class ConfiguracaoRondaSabado(models.Model):
    sabado      = models.OneToOneField('sabado.Sabado', on_delete=models.CASCADE, related_name='configuracao_ronda')
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDENTE_SORTEIO')
    dia_de_evento = models.BooleanField(default=False, help_text='Ronda rotativa: 2 grupos fixos por local (tamanho definido em cada local), sem horários.')
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
    hora_inicio  = models.TimeField(null=True, blank=True)
    hora_fim     = models.TimeField(null=True, blank=True)
    local        = models.ForeignKey(LocalRonda, on_delete=models.PROTECT, related_name='horarios', null=True)
    ordem        = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordem', 'hora_inicio', 'local__nome']
        unique_together = ('configuracao', 'hora_inicio', 'hora_fim', 'local')
        verbose_name = 'Horário de Ronda'
        verbose_name_plural = 'Horários de Ronda'

    def __str__(self):
        base = f'{self.hora_inicio:%H:%M}–{self.hora_fim:%H:%M}'
        return f'{base} · {self.local.nome}' if self.local_id else base


class EscalaRonda(models.Model):
    horario             = models.ForeignKey(HorarioRonda, on_delete=models.CASCADE, related_name='escalas')
    local               = models.ForeignKey(LocalRonda, on_delete=models.PROTECT, related_name='escalas')
    voluntario          = models.ForeignKey('voluntario.Voluntario', on_delete=models.CASCADE, related_name='escalas_ronda')
    is_substituto       = models.BooleanField(default=False)
    voluntario_original = models.ForeignKey('voluntario.Voluntario', on_delete=models.SET_NULL, null=True, blank=True, related_name='escalas_substituidas')
    dupla               = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Grupo fixo (1 ou 2) no modo dia de evento.')
    criado_em           = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('horario', 'local', 'voluntario')
        verbose_name = 'Escala de Ronda'
        verbose_name_plural = 'Escalas de Ronda'

    def clean(self):
        if self.horario_id and self.horario.configuracao.dia_de_evento:
            limite = self.local.total_evento if self.local_id else 4
        else:
            limite = 2
        count = EscalaRonda.objects.filter(horario=self.horario, local=self.local).exclude(pk=self.pk).count()
        if count >= limite:
            raise ValidationError(f'Máximo de {limite} voluntários por local e horário.')

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
