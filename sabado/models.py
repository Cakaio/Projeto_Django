from django.db import models
from django.utils import timezone
from datetime import timedelta
import datetime

# Create your models here.
def proximo_sabado():
    """Retorna a data do próximo sábado a partir de hoje."""
    # localdate(), não now().date(): com USE_TZ=True o now() é UTC, e .date()
    # nele vira o dia seguinte a partir das 21h de São Paulo.
    hoje = timezone.localdate()
    dias_ate_sabado = (5 - hoje.weekday()) % 7  # 5 = sábado (0 = segunda)
    if dias_ate_sabado == 0:
        dias_ate_sabado = 7  # se hoje já for sábado, pega o próximo
    return hoje + datetime.timedelta(days=dias_ate_sabado)

class Sabado(models.Model):
    data = models.DateField(unique=True, default=proximo_sabado)
    tema = models.CharField(max_length=200)
    descricao = models.TextField()
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.data.strftime('%d/%m/%Y')

    @property
    def enquete_aberta(self):
        """A enquete aceita resposta até o penúltimo dia antes do sábado.

        Esta é a ÚNICA regra de fechamento do sistema: a view de resposta
        (sabado/views.py), a tela inicial e o resumo consultam esta propriedade.
        O lembrete diário também — antes ele fazia a conta por conta própria com
        `data - 3 dias`, divergindo daqui em dois dias e mandando "fecha amanhã"
        na terça, quando a pessoa ainda podia responder quarta e quinta.

        `localdate()` em vez de `now().date()`: com USE_TZ=True o now() é UTC, e
        a partir das 21h de São Paulo o .date() já é o dia seguinte — a enquete
        fechava uma noite antes para quem abria o site tarde.
        """
        hoje = timezone.localdate()
        data_fechamento = self.data - timedelta(days=1)
        return hoje < data_fechamento

    @property
    def dias_para_fechar(self):
        """Quantos dias ainda restam para responder, contando hoje.

        Serve ao texto do lembrete diário, que não pode mais dizer "fecha
        amanhã" todo dia. Devolve 0 quando a enquete já fechou.
        """
        if not self.enquete_aberta:
            return 0
        return (self.data - timedelta(days=1) - timezone.localdate()).days


class FaixaHorarioAjuda(models.Model):
    codigo = models.CharField(max_length=10, unique=True)
    descricao = models.CharField(max_length=50)

    def __str__(self):
        return self.descricao    

class DisponibilidadeVoluntario(models.Model):
    sabado = models.ForeignKey(Sabado,on_delete=models.CASCADE,related_name="disponibilidades")
    voluntario = models.ForeignKey("voluntario.Voluntario",on_delete=models.CASCADE,related_name="disponibilidades")
    vai_ao_projeto = models.BooleanField(null=False, default=True)
    pode_ajudar = models.ManyToManyField(FaixaHorarioAjuda,blank=True)
    saude = models.BooleanField(null=True, default=True)
    vai_de_carro = models.BooleanField(null=True)
    respondido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("sabado", "voluntario")

