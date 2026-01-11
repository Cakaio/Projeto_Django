from django.db import models
from django.utils import timezone
import datetime

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
COMPETENCIAS_SALAS = {
    "VIOLETA": ["Respeito","Sentimentos","Imaginação"],
    "ANIL": ["Ampliação de visão de mundo e tolerância","Criatividade","Comunicação e introdução à leitura","Prática sensorial e coordenação motora","Concentração e memória",],
    "AZUL": ["Cooperação e relações interpessoais","Empatia","Responsabilidade e consequência","Criatividade","Incentivo à leitura e escrita",],
    "VERDE": ["Trabalho em equipe","Consciência social","Autonomia","Liderança","Autoconhecimento",],
    "AMARELO": ["Trabalho em equipe","Consciência social","Expressão de opinião","Comunicação",],
    "LARANJA": ["Quebra de panelinhas","Senso crítico","Responsabilidade","Vínculo","Projeção de futuro",],
    "VERMELHO": ["Pensamento crítico","Autonomia","Relacionamento interpessoal","Visão global","Reinventar seu lugar no mundo",],
    "FAMILIA_FELIZ": ["Cidadania","Quem sou eu?","Reinventar meu lugar no mundo","Resiliência emocional",],
}

def proximo_sabado():
    """Retorna a data do próximo sábado a partir de hoje."""
    hoje = timezone.now().date()
    dias_ate_sabado = (5 - hoje.weekday()) % 7  # 5 = sábado (0 = segunda)
    if dias_ate_sabado == 0:
        dias_ate_sabado = 7  # se hoje já for sábado, pega o próximo
    return hoje + datetime.timedelta(days=dias_ate_sabado)

UNIDADES = (
    ("UN", "Unidade"),
    ("PAC", "Pacote"),
    ("CX", "Caixa"),
    ("TUBO", "Tubo"),
    ("METRO", "Metro"),
    ("L", "Litro"),
    ("KG", "Quilo"),
    ("OUTROS", "Outros"),
)

class Semanario(models.Model):
    tema = models.CharField(max_length=100, blank=True, null=True)
    sala = models.CharField(max_length=20, choices=LISTA_SALAS)
    data = models.DateField(default=proximo_sabado)

    def __str__(self):
        return f"{self.sala} - {self.data.strftime('%d/%m/%Y')}"

class Atividade(models.Model):
    semanario = models.ForeignKey(Semanario,on_delete=models.CASCADE,related_name="atividades")
    atividade = models.CharField(max_length=100)
    descricao = models.TextField()
    competencia = models.CharField(max_length=50)
    fotos = models.ImageField(upload_to='fotos_atividades', blank=True, null=True)
    tempo_atividade = models.PositiveIntegerField(help_text="Tempo da atividade em minutos", blank=True, null=True) 
    feedback = models.TextField(blank=True, null=True)
    responsavel = models.ForeignKey("voluntario.Voluntario",on_delete=models.SET_NULL,null=True,blank=True,related_name="atividades_responsavel")

    def __str__(self):
        return f"{self.atividade} ({self.semanario.sala} - {self.semanario.data.strftime('%d/%m/%Y')})"

class Material(models.Model):
    atividade = models.ForeignKey(Atividade,on_delete=models.CASCADE,related_name="materiais")
    nome = models.CharField(max_length=100)
    quantidade = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    unidade = models.CharField(max_length=10, choices=UNIDADES, default="UN")

    def __str__(self):
        return f"{self.nome} ({self.atividade.semanario.sala} - {self.atividade.semanario.data.strftime('%d/%m/%Y')})"