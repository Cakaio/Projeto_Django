"""Reetiqueta os alertas automáticos de falta que já estão no banco.

Os dois geradores automáticos apontavam para regras de julgamento humano:
  AL13 – "Faltou a um sábado sem avisar e o líder julgou pertinente"
  AL2  – "Confirmou presença e não compareceu no sábado"

Nenhuma das duas descreve o que o sistema mediu (3 faltas consecutivas). A
liderança lia o texto e não reconhecia o caso — o alerta chegava sem sentido
para quem tinha que cobrar. Corrigir só o código deixaria as ocorrências
antigas mentindo na tela, então elas passam para a AL18.

Só mexe em `automatico=True`: alerta aplicado por uma pessoa é decisão dela e
não se reescreve, mesmo que use a mesma regra.
"""
from django.db import migrations

REGRAS_ERRADAS = ['AL13', 'AL2']
REGRA_CERTA = 'AL18'


def apontar_para_a_regra_certa(apps, schema_editor):
    Ocorrencia = apps.get_model('voluntario', 'Ocorrencia')
    Ocorrencia.objects.filter(
        tipo='ALERTA', automatico=True, regra__in=REGRAS_ERRADAS,
    ).update(regra=REGRA_CERTA)


def nao_da_para_desfazer(apps, schema_editor):
    """Os alertas vinham de duas regras diferentes e viraram uma.

    Reverter teria que adivinhar qual ocorrência era AL13 e qual era AL2 —
    melhor não fingir que dá.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('voluntario', '0014_alter_voluntario_managers'),
    ]

    operations = [
        migrations.RunPython(apontar_para_a_regra_certa, nao_da_para_desfazer),
    ]
