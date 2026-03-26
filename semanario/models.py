from django.db import models
from django.utils import timezone
import datetime
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
COMPETENCIAS_SALAS = {
    "VIOLETA": ["Respeito","Sentimentos","Imaginação","Recreativos"],
    "ANIL": ["Ampliação de visão de mundo e tolerância","Criatividade","Comunicação e introdução à leitura","Prática sensorial e coordenação motora","Concentração e memória","Recreativos"],
    "AZUL": ["Cooperação e relações interpessoais","Empatia","Responsabilidade e consequência","Criatividade","Incentivo à leitura e escrita","Recreativos"],
    "VERDE": ["Trabalho em equipe","Consciência social","Autonomia","Liderança","Autoconhecimento","Recreativos"],
    "AMARELO": ["Trabalho em equipe","Consciência social","Expressão de opinião","Comunicação","Recreativos"],
    "LARANJA": ["Quebra de panelinhas","Senso crítico","Responsabilidade","Vínculo","Projeção de futuro","Recreativos"],
    "VERMELHO": ["Pensamento crítico","Autonomia","Relacionamento interpessoal","Visão global","Reinventar seu lugar no mundo","Recreativos"],
    "FAMILIA_FELIZ": ["Cidadania","Quem sou eu?","Reinventar meu lugar no mundo","Resiliência emocional","Recreativos"],
}

DIMENSOES_COMPETENCIAS = {
    "Desenvolvimento Socioemocional e Relacional": [
        "Respeito",
        "Sentimentos",
        "Cooperação e relações interpessoais",
        "Empatia",
        "Trabalho em equipe",
        "Vínculo",
        "Quebra de panelinhas",
        "Relacionamento interpessoal",
    ],

    "Autoconhecimento, Identidade e Projeto de Vida": [
        "Autoconhecimento",
        "Projeção de futuro",
        "Reinventar seu lugar no mundo",
        "Visão global",
        "Quem sou eu",
    ],

    "Autonomia, Responsabilidade e Protagonismo": [
        "Responsabilidade e consequência",
        "Autonomia",
        "Liderança",
        "Responsabilidade",
        "Resiliência emocional",
    ],

    "Pensamento Crítico e Consciência Social": [
        "Ampliação de visão de mundo e tolerância",
        "Consciência social",
        "Senso crítico",
        "Pensamento crítico",
        "Cidadania",
    ],

    "Criatividade, Expressão e Comunicação": [
        "Imaginação",
        "Criatividade",
        "Prática sensorial e coordenação motora",
        "Expressão de opinião",
        "Comunicação",
    ],

    "Aprendizagem Cognitiva e Desenvolvimento Intelectual": [
        "Comunicação e introdução à leitura",
        "Concentração e memória",
        "Incentivo à leitura e escrita",
    ],
    "Recreativos": [
        "Recreativos",
    ],
}


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

LOCAIS = (
    ("SALINHA", "Salinha"),
    ("FF", "FF"),
    ("CAMPO", "Campo"),
    ("RANCHO", "Rancho"),
    ("PRAÇA", "Praça"),
    ("RU", "RU"),
    ("OUTROS", "Outros"),
)

TIPO_LOCAL = (
    ("MERCADO", "Mercado"),
    ("PAPELARIA", "Papelaria"),
    ("SALINHA", "Salinha"),
    ("ARTIGO DE FESTA", "Artigo de Festa"),
    ("OUTROS", "Outros")
)

PEDIDO = (
    ("SUPPLY", "Supply"),
    ("RECREA", "Recrea"),
    ("ZUERO", "Zuero"),
    ("OUTROS", "Outros")
)

class Semanario(models.Model):
    tema = models.CharField(max_length=100, blank=True, null=True)
    sala = models.CharField(max_length=20, choices=LISTA_SALAS)
    data = models.ForeignKey(Sabado,on_delete=models.CASCADE,related_name="semanarios")
    projetor = models.BooleanField(default=False)
    vagas = models.PositiveIntegerField(default=0)
    talentos_necessarios = models.ManyToManyField("voluntario.Talento", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sala} - {self.data.data.strftime('%d/%m/%Y')}"
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["data", "sala"], name="uniq_semanario_por_sabado_sala")
        ]

class Atividade(models.Model):
    semanario = models.ForeignKey(Semanario,on_delete=models.CASCADE,related_name="atividades")
    atividade = models.CharField(max_length=100)
    descricao = models.TextField()
    local = models.CharField(max_length=100, choices=LOCAIS, blank=True, null=True, default="SALINHA")
    competencia = models.CharField(max_length=50)
    dimensao_competencia = models.CharField(max_length=200, editable=False, blank=True, null=True)
    fotos = models.ImageField(upload_to='fotos_atividades', blank=True, null=True)
    tempo_atividade = models.PositiveIntegerField(help_text="Tempo da atividade em minutos", blank=True, null=True) 
    feedback = models.TextField(blank=True, null=True)
    responsavel = models.ForeignKey("voluntario.Voluntario",on_delete=models.SET_NULL,null=True,blank=True,related_name="atividades_responsavel")

    def __str__(self):
        return f"{self.atividade} {self.semanario.sala}"
    
    def save(self, *args, **kwargs):
        self.dimensao_competencia = self.get_dimensao_por_competencia()
        super().save(*args, **kwargs)

    def get_dimensao_por_competencia(self):
        if not self.competencia:
            return ""

        for dimensao, competencias in DIMENSOES_COMPETENCIAS.items():
            if self.competencia.strip().lower() in [
                c.lower() for c in competencias
            ]:
                return dimensao

        return "Não classificada"

class Material(models.Model):
    atividade = models.ForeignKey(Atividade,on_delete=models.CASCADE,related_name="materiais")
    nome = models.CharField(max_length=100)
    quantidade = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    unidade = models.CharField(max_length=10, choices=UNIDADES, default="UN")
    valor = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    local_compra = models.CharField(max_length=100, blank=True, null=True)
    tipo_local = models.CharField(max_length=100, choices=TIPO_LOCAL, blank=True, null=True)
    pedido = models.CharField(max_length=100, choices=PEDIDO, blank=True, null=True)

    def __str__(self):
        return f"{self.nome} ({self.atividade.semanario.sala})"