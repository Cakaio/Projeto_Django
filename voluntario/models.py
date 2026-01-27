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

FACULDADES = (
    ("EEL-USP", "EEL-USP"),
    ("SERRA DOURADA", "Serra Dourada"),
    ("UNISAL", "Unisal"),
    ("UNIFATEA", "Unifatea"),
    ("OUTRA", "Outra"),
    ("NAO_ESTUDANTE", "Não Estudante")
)

CURSOS = (
    ("ENGENHARIA_QUÍMICA", "Engenharia Química"),
    ("ENGENHARIA_DE_PRODUÇÃO", "Engenharia de Produção"),
    ("ENGENHARIA_FÍSICA", "Engenharia Física"),
    ("ENGENHARIA_AMBIENTAL", "Engenharia Ambiental"),
    ("ENGENHARIA_DE_MATERIAIS", "Engenharia de Materiais"),
    ("ENGENHARIA_BIOQUÍMICA", "Engenharia Bioquímica"),
    ("PSICOLOGIA", "Psicologia"),
    ("OUTRO", "Outro"),
    ("NAO_ESTUDANTE", "Não Estudante")
)
TIPO_ALIMENTACAO = (
    ("ONIVORO", "Onívoro"),
    ("VEGETARIANO", "Vegetariano"),
    ("VEGANO", "Vegano")
)

class Voluntario(AbstractUser):
    area = models.CharField(max_length=30, choices=LISTA_AREAS)
    apelido = models.CharField(max_length=50, blank=True, null=True)
    data_nascimento = models.DateField(blank=True, null=True)
    celular = models.CharField(max_length=15, blank=True, null=True, help_text="Formato: DDD + número, apenas números")
    instagram = models.CharField(max_length=50, blank=True, null=True)
    email_alternativo = models.EmailField(blank=True, null=True)
    endereco = models.CharField(max_length=200, blank=True, null=True, help_text="Endereço de Lorena de preferência")
    republica = models.CharField(max_length=100, blank=True, null=True)
    rg = models.CharField(max_length=15, blank=True, null=True)
    foto = models.ImageField(upload_to='fotos_voluntarios', blank=True, null=True)
    restricao_alimentar = models.CharField(max_length=100, blank=True, null=True)
    alimentacao = models.CharField(max_length=20,choices=TIPO_ALIMENTACAO,blank=True,null=True)
    comida_favorita = models.CharField(max_length=100, blank=True, null=True)
    alergia = models.CharField(max_length=100, blank=True, null=True)
    medicacao_continua = models.CharField(max_length=100, blank=True, null=True)
    faculdade = models.CharField(max_length=100, choices=FACULDADES, blank=True, null=True)
    n_usp = models.CharField(max_length=20, blank=True, null=True)
    email_usp = models.EmailField(blank=True, null=True)
    curso = models.CharField(max_length=100, choices=CURSOS, blank=True, null=True)
    ano_faculdade = models.IntegerField(blank=True, null=True)
    trabalha = models.BooleanField(default=False)
    empresa = models.CharField(max_length=100, blank=True, null=True)
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
    registrado_por = models.ForeignKey("Voluntario",on_delete=models.SET_NULL,blank=True,null=True,related_name="presencas_registradas_voluntarios")

    def __str__(self):
        return f"{self.voluntario.username} - {self.data} ({self.get_presenca_display()})"
    
class Talento(models.Model):
    talento = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['talento']

    def __str__(self):
        return self.talento