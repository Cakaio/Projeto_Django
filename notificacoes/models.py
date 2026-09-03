from django.conf import settings
from django.db import models

# As 7 salas (VIOLETA…VERMELHO) e FAMILIA_FELIZ são valores de LISTA_AREAS, no
# mesmo campo Voluntario.area das áreas funcionais. Por isso NÃO existe um
# destino "por sala" separado: ele filtraria exatamente o mesmo campo que AREA.
DESTINO_CHOICES = [
    ("TODOS", "Todos os voluntários"),
    ("AREA", "Por área"),
]


class InscricaoPush(models.Model):
    """Um aparelho+navegador inscrito para receber push.

    Um voluntário tem várias: celular, tablet, desktop do escritório.
    """
    voluntario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="inscricoes_push",
    )
    # Endpoints do FCM passam de 200 caracteres com folga.
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    ultimo_ok = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "inscrição push"
        verbose_name_plural = "inscrições push"
        ordering = ("-criado_em",)

    def __str__(self):
        return f"{self.voluntario} — {self.user_agent or 'aparelho desconhecido'}"


class Aviso(models.Model):
    """Registro de um aviso disparado manualmente pela gestão.

    Os outros gatilhos de push já deixam rastro nos modelos deles (Ocorrencia,
    Pedido, DisponibilidadeVoluntario), então não replicamos registro aqui.
    """
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="avisos_enviados",
    )
    # Android trunca notificação longa e o iOS mostra ~4 linhas: os limites
    # existem para o texto caber na tela do aparelho.
    titulo = models.CharField(max_length=80)
    mensagem = models.CharField(max_length=300)
    destino = models.CharField(max_length=10, choices=DESTINO_CHOICES)
    alvo = models.CharField(max_length=30, blank=True, help_text="Valor de LISTA_AREAS")
    criado_em = models.DateTimeField(auto_now_add=True)
    total_enviado = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "aviso"
        verbose_name_plural = "avisos"
        ordering = ("-criado_em",)

    def __str__(self):
        return f"{self.titulo} ({self.criado_em:%d/%m/%Y})"
