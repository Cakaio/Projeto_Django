from datetime import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from sabado.models import DisponibilidadeVoluntario, Sabado
from voluntario.models import LISTA_AREAS, Voluntario
from .validators import validar_participante, validar_periodo


class EscalaAjuda(models.Model):
    class Status(models.TextChoices):
        RASCUNHO = "RASCUNHO", "Rascunho"
        PUBLICADA = "PUBLICADA", "Publicada"

    sabado = models.OneToOneField(Sabado, on_delete=models.CASCADE, related_name="escala_ajudas")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RASCUNHO)
    revisao = models.PositiveIntegerField(default=1, editable=False)
    publicada_em = models.DateTimeField(null=True, blank=True, editable=False)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-sabado__data"]
        verbose_name = "Escala de ajudas"
        verbose_name_plural = "Escalas de ajudas"
        constraints = [models.CheckConstraint(
            check=(models.Q(status="RASCUNHO", publicada_em__isnull=True)
                   | models.Q(status="PUBLICADA", publicada_em__isnull=False)),
            name="ajudas_status_publicacao_consistente",
        )]

    def __str__(self):
        return f"{self.sabado} — {self.get_status_display()}"


class NecessidadeAjuda(models.Model):
    escala = models.ForeignKey(EscalaAjuda, on_delete=models.CASCADE, related_name="necessidades")
    area = models.CharField(max_length=30, choices=LISTA_AREAS)
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()
    quantidade = models.PositiveIntegerField("pessoas necessárias", default=1)

    class Meta:
        ordering = ["hora_inicio", "area"]
        constraints = [models.CheckConstraint(
            check=models.Q(hora_inicio__lt=models.F("hora_fim")), name="necessidade_horarios_em_ordem")]

    def clean(self):
        super().clean()
        if self.escala_id and EscalaAjuda.objects.filter(pk=self.escala_id).exists():
            validar_periodo(self.hora_inicio, self.hora_fim, self.escala.sabado)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_area_display()} · {self.hora_inicio:%H:%M}–{self.hora_fim:%H:%M}"


class Ajuda(models.Model):
    # O sábado vem da escala, evitando duas FKs que poderiam discordar.
    escala = models.ForeignKey(EscalaAjuda, on_delete=models.CASCADE, related_name="ajudas")
    voluntario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ajudas")
    area_destino = models.CharField(max_length=30, choices=LISTA_AREAS)
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()

    class Meta:
        ordering = ["hora_inicio", "area_destino", "voluntario__first_name"]
        constraints = [models.CheckConstraint(
            check=models.Q(hora_inicio__lt=models.F("hora_fim")), name="ajuda_horarios_em_ordem")]
        indexes = [models.Index(fields=["escala", "voluntario", "hora_inicio"])]

    @property
    def sabado(self):
        return self.escala.sabado

    def clean(self):
        super().clean()
        if not self.escala_id or not EscalaAjuda.objects.filter(pk=self.escala_id).exists():
            return
        validar_periodo(self.hora_inicio, self.hora_fim, self.sabado)
        voluntario = Voluntario.objects.filter(pk=self.voluntario_id).first()
        if not voluntario:
            return  # A validação da ForeignKey informa o voluntário inexistente.
        confirmado = DisponibilidadeVoluntario.objects.filter(
            sabado=self.sabado, voluntario=voluntario, vai_ao_projeto=True).exists()
        validar_participante(voluntario, self.area_destino, confirmado)
        if isinstance(self.hora_inicio, time) and isinstance(self.hora_fim, time) and Ajuda.objects.filter(
                escala=self.escala, voluntario=voluntario,
                hora_inicio__lt=self.hora_fim, hora_fim__gt=self.hora_inicio).exclude(pk=self.pk).exists():
            raise ValidationError("Este voluntário já tem uma ajuda nesse horário.")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            # A mesma ordem de travas do serviço de salvamento.
            if self.escala_id:
                escala = EscalaAjuda.objects.filter(pk=self.escala_id).first()
                if escala:
                    Sabado.objects.select_for_update().get(pk=escala.sabado_id)
            self.full_clean()
            return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.voluntario} → {self.get_area_destino_display()} ({self.sabado})"
