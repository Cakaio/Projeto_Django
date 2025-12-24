from django.db import models
from django.utils import timezone

# Create your models here.
LISTA_SALAS = (
    ("VIOLETA", "Violeta"),
    ("ANIL", "Anil"),
    ("AZUL", "Azul"),
    ("VERDE", "Verde"),
    ("AMARELO", "Amarelo"),
    ("LARANJA", "Laranja"),
    ("VERMELHO", "Vermelho"),
    ("FAMILIA_FELIZ", "Família Feliz"),
)

class Atendido(models.Model):
    nome = models.CharField(max_length=50)
    data_nascimento = models.DateField()
    responsavel = models.CharField(max_length=50)
    sala = models.CharField(max_length=20, choices=LISTA_SALAS)
    rg = models.CharField(max_length=15, blank=True, null=True)
    cpf = models.CharField(max_length=14, unique=True, blank=True, null=True)
    foto = models.ImageField(upload_to='fotos_atendidos', blank=True, null=True)
    data_criacao = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.nome