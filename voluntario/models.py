from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractUser

from sabado.models import Sabado

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
    instagram = models.CharField(max_length=50, blank=True, null=True)
    email_alternativo = models.EmailField(blank=True, null=True)
    endereco = models.CharField(max_length=200, blank=True, null=True)
    republica = models.CharField(max_length=100, blank=True, null=True)
    rg = models.CharField(max_length=15, blank=True, null=True)
    foto = models.ImageField(upload_to='fotos_voluntarios', blank=True, null=True)
    restricao_alimentar = models.TextField(blank=True, null=True)

    TIPO_ALIMENTACAO = (("ONIVORO", "Onívoro"),("VEGETARIANO", "Vegetariano"),("VEGANO", "Vegano"))
    
    alimentacao = models.CharField(max_length=20,choices=TIPO_ALIMENTACAO,blank=True,null=True)
    alergia = models.TextField(blank=True, null=True)
    medicacao_continua = models.TextField(blank=True, null=True)
    faculdade = models.CharField(max_length=100, blank=True, null=True)
    curso = models.CharField(max_length=100, blank=True, null=True)
    talentos = models.ManyToManyField("Talento", blank=True)
    data_entrada = models.DateField(default=timezone.now)
    data_saida = models.DateField(blank=True, null=True)
    

    def __str__(self):
        return self.get_full_name() or self.username

class PresencaVoluntario(models.Model):
    OPCOES_PRESENCA = [
        ("PRESENTE", "Presente"),
        ("AUSENTE", "Ausente"),
        ("JUSTIFICADA", "Falta Justificada"),
    ]

    voluntario = models.ForeignKey("Voluntario",on_delete=models.CASCADE,related_name="presencas")
    presenca = models.CharField(max_length=15,choices=OPCOES_PRESENCA,default="PRESENTE")
    data = models.ForeignKey(Sabado,on_delete=models.CASCADE,related_name="presencas_voluntarios")

    def __str__(self):
        return f"{self.voluntario.username} - {self.data} ({self.get_presenca_display()})"
    
class Talento(models.Model):
    talento = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['talento']

    def __str__(self):
        return self.talento