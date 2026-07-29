from django.conf import settings
from django.db import models

from voluntario.models import Grupo, LISTA_AREAS


class Pauta(models.Model):
    STATUS = (
        ("A_FAZER", "A fazer"),
        ("EM_EXECUCAO", "Em execução"),
        ("BLOQUEADA", "Bloqueada"),
        ("FINALIZADA", "Finalizada"),
    )

    titulo = models.CharField(max_length=180)
    descricao = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS, default="A_FAZER")
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pautas_criadas",
    )
    emitido_por_area = models.CharField(
        max_length=30,
        choices=LISTA_AREAS,
        help_text="Área do autor no momento em que a pauta foi criada.",
    )
    ddl = models.DateTimeField("prazo")
    grupo = models.ForeignKey(
        Grupo,
        on_delete=models.PROTECT,
        related_name="pautas",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ddl", "-criado_em"]
        verbose_name = "Pauta"
        verbose_name_plural = "Pautas"

    def __str__(self):
        return self.titulo

    @property
    def status_cor(self):
        return {
            "A_FAZER": "#64748b",
            "EM_EXECUCAO": "#2563eb",
            "BLOQUEADA": "#dc2626",
            "FINALIZADA": "#16845b",
        }.get(self.status, "#64748b")


class ComentarioPauta(models.Model):
    pauta = models.ForeignKey(
        Pauta,
        on_delete=models.CASCADE,
        related_name="comentarios",
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="comentarios_em_pautas",
    )
    texto = models.TextField(max_length=2000)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em"]
        verbose_name = "Comentário de pauta"
        verbose_name_plural = "Comentários de pautas"

    def __str__(self):
        return f"{self.autor} em {self.pauta}"


class CienciaPauta(models.Model):
    pauta = models.ForeignKey(
        Pauta,
        on_delete=models.CASCADE,
        related_name="ciencias",
    )
    voluntario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ciencias_de_pautas",
    )
    ciente_em = models.DateTimeField(auto_now_add=True)
    ocultada = models.BooleanField(default=False)
    ocultada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["pauta", "voluntario"],
                name="ciencia_unica_por_voluntario_e_pauta",
            ),
        ]
        verbose_name = "Ciência de pauta"
        verbose_name_plural = "Ciências de pautas"

    def __str__(self):
        return f"{self.voluntario} ciente de {self.pauta}"
