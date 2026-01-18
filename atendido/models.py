from django.db import models
from django.utils import timezone

from sabado.models import Sabado

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
    familia = models.ForeignKey("Familia", on_delete=models.SET_NULL, null=True, blank=True, related_name="atendidos")
    nome = models.CharField(max_length=50)
    data_nascimento = models.DateField()
    sala = models.CharField(max_length=20, choices=LISTA_SALAS)
    rg = models.CharField(max_length=15, blank=True, null=True)
    cpf = models.CharField(max_length=14, unique=True, blank=True, null=True)
    foto = models.ImageField(upload_to='fotos_atendidos', blank=True, null=True)
    data_criacao = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.nome
    
class Familia(models.Model):
    nome = models.CharField(max_length=50)
    data_nascimento = models.DateField()
    renda = models.DecimalField(max_digits=10, decimal_places=2)
    cpf = models.CharField(max_length=14, unique=True, blank=True, null=True)
    data_criacao = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.nome

class PresencaAtendido(models.Model):
    OPCOES_PRESENCA = [
        ("PRESENTE", "Presente"),
        ("AUSENTE", "Ausente"),
        ("JUSTIFICADA", "Falta Justificada"),
    ]
    atendido = models.ForeignKey("Atendido",on_delete=models.CASCADE,related_name="presencas")
    presenca = models.CharField(max_length=15,choices=OPCOES_PRESENCA,default="PRESENTE")
    data = models.ForeignKey(Sabado,on_delete=models.CASCADE,related_name="presencas_atendidos")
    registrado_por = models.ForeignKey("voluntario.Voluntario",on_delete=models.SET_NULL,null=True,blank=True,related_name="presencas_registradas_atendidos")

    def __str__(self):
        return f"{self.atendido.nome} - {self.data} ({self.get_presenca_display()})"


