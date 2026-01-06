from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser

LISTA_AREAS = (
    ("VIOLETA", "Violeta"),
    ("ANIL", "Anil"),
    ("AZUL", "Azul"),
    ("VERDE", "Verde"),
    ("AMARELO", "Amarelo"),
    ("LARANJA", "Laranja"),
    ("VERMELHO", "Vermelho"),
    ("FAMILIA_FELIZ", "Família Feliz"),
    ("MARKETING", "Marketing"),
    ("ADM/FIN", "Adm/Fin"),
    ("CR/RE", "Cr/Re"),
    ("EVENTOS", "Eventos"),
    ("GESTAO_DE_TALENTOS", "Gestão de Talentos"),
    ("RECREACAO", "Recreação"),
    ("SUPPLY", "Supply"),
    ("PROJETOS", "Projetos"),
    ("TRIADE", "Tríade"),
)

class Voluntario(AbstractUser):
    area = models.CharField(max_length=30, choices=LISTA_AREAS)
    apelido = models.CharField(max_length=50, blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)
    celular = models.CharField(max_length=15, blank=True, null=True)
    rg = models.CharField(max_length=15, blank=True, null=True)
    foto = models.ImageField(upload_to='fotos_voluntarios', blank=True, null=True)
    data_entrada_projeto = models.DateField(default=timezone.now)
    data_saida_projeto = models.DateField(blank=True, null=True)

    def __str__(self):
        return self.get_full_name() or self.username

class PresencaVoluntario(models.Model):
    OPCOES_PRESENCA = [
        ("PRESENTE", "Presente"),
        ("AUSENTE", "Ausente"),
        ("JUSTIFICADA", "Falta Justificada"),
    ]

    voluntario = models.ForeignKey(
        "Voluntario",
        on_delete=models.CASCADE,
        related_name="presencas"
    )
    presenca = models.CharField(
        max_length=15,
        choices=OPCOES_PRESENCA,
        default="PRESENTE"
    )
    data = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.voluntario.username} - {self.data} ({self.get_presenca_display()})"