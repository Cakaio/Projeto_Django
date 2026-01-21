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
    responsavel = models.ManyToManyField("ResponsavelAtendido", blank=True, related_name="atendidos")
    nome = models.CharField(max_length=50)
    data_nascimento = models.DateField()
    sala = models.CharField(max_length=20, choices=LISTA_SALAS)
    pai = models.CharField(max_length=50, blank=True, null=True)
    mae = models.CharField(max_length=50, blank=True, null=True)
    rg = models.CharField(max_length=15, blank=True, null=True)
    cpf = models.CharField(max_length=14, unique=True, blank=True, null=True)
    contato = models.CharField(max_length=20, blank=True, null=True)
    escolaridade = models.CharField(max_length=100, blank=True, null=True)
    #escola = models.CharField(max_length=100, blank=True, null=True) Tabela de escolas?
    trabalho = models.CharField(max_length=100, blank=True, null=True)
    foto = models.ImageField(upload_to='fotos_atendidos', blank=True, null=True)
    projeto_social = models.CharField(max_length=100, blank=True, null=True)
    convenio_medico = models.CharField(max_length=100, blank=True, null=True)
    vacina_covid = models.BooleanField(default=False)
    restricao_alimentar = models.TextField(blank=True, null=True)
    restricao_medica = models.TextField(blank=True, null=True)
    medicacao_continua = models.TextField(blank=True, null=True)
    identidade_etnica = models.CharField(max_length=50, blank=True, null=True)
    numeracao_camisa = models.CharField(max_length=5, blank=True, null=True)
    numeracao_calca = models.CharField(max_length=5, blank=True, null=True)
    numeracao_calcado = models.CharField(max_length=5, blank=True, null=True)
    termos_assinado = models.BooleanField(default=False)
    registrado_por = models.ForeignKey("voluntario.Voluntario",on_delete=models.SET_NULL,null=True,blank=True,related_name="atendidos_registrados")
    data_criacao = models.DateTimeField(default=timezone.now)

    
class Familia(models.Model):
    nome = models.CharField(max_length=50, blank=True, null=True)
    cep = models.CharField(max_length=10, blank=True, null=True)
    endereco = models.CharField(max_length=200, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    agua_encanada = models.BooleanField(default=False)
    esgoto_encanado = models.BooleanField(default=False)
    energia_eletrica = models.BooleanField(default=False)
    renda_total_familia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pessoas_moram_familia = models.IntegerField(default=1)
    pessoas_trabalham_familia = models.IntegerField(default=0)
    programa_transferencia_renda = models.BooleanField(default=False)
    internet_casa = models.BooleanField(default=False)
    comodos_casa = models.IntegerField(default=0)
    situacao_moradia = models.CharField(max_length=100, blank=True, null=True)
    tv_casa = models.IntegerField(default=0)
    banheiro_casa = models.IntegerField(default=0)
    motos_casa = models.IntegerField(default=0)
    carros_casa = models.IntegerField(default=0)
    geladeira_casa = models.IntegerField(default=0)
    freezer_casa = models.IntegerField(default=0)
    celular_casa = models.IntegerField(default=0)
    computador_casa = models.IntegerField(default=0)
    cesta_natal = models.BooleanField(default=False)
    data_criacao = models.DateTimeField(default=timezone.now)

class ResponsavelAtendido(models.Model):
    nome = models.CharField(max_length=50, blank=True, null=True)
    cpf = models.CharField(max_length=14, unique=True, null=True, blank=True)
    rg = models.CharField(max_length=15, blank=True, null=True)
    parentesco = models.CharField(max_length=50, null=True, blank=True)
    contato = models.CharField(max_length=20, blank=True, null=True)
    outro_contato = models.CharField(max_length=20, blank=True, null=True)
    trabalho = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    escolaridade = models.CharField(max_length=100, blank=True, null=True)
    data_criacao = models.DateTimeField(default=timezone.now)

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


