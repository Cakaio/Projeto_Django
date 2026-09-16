"""Um e-mail, um voluntário — quando o e-mail está preenchido.

Esta migration pode FALHAR num banco que já tem duplicata, e isso é de
propósito: um índice único não nasce por cima de dado que o contradiz. Mas uma
migration que estoura com `IntegrityError` no meio do deploy só diz "deu ruim",
e quem está no servidor às sete da manhã de sábado não tem como saber QUAIS
cadastros brigaram.

Por isso a conferência vem ANTES, em Python, e a mensagem nomeia os culpados.
"""
from django.db import migrations, models
from django.db.models import Count
from django.db.models.functions import Lower


class EmailDuplicado(Exception):
    """Falha com instrução, não com traceback de banco."""


def conferir_antes(apps, schema_editor):
    Voluntario = apps.get_model('voluntario', 'Voluntario')

    repetidos = (Voluntario.objects
                 .exclude(email='')
                 .exclude(email__isnull=True)
                 .annotate(chave=Lower('email'))
                 .values('chave')
                 .annotate(quantos=Count('id'))
                 .filter(quantos__gt=1)
                 .order_by('chave'))

    linhas = []
    for grupo in repetidos:
        donos = (Voluntario.objects
                 .annotate(chave=Lower('email'))
                 .filter(chave=grupo['chave'])
                 .order_by('id')
                 .values_list('id', 'username'))
        quem = ', '.join(f'#{pk} {nome}' for pk, nome in donos)
        linhas.append(f'  {grupo["chave"]} -> {quem}')

    if not linhas:
        return

    raise EmailDuplicado(
        'Não dá para exigir e-mail único: há cadastros repetidos.\n\n'
        + '\n'.join(linhas)
        + '\n\nO que fazer: no admin, deixe o e-mail em UM cadastro de cada '
          'linha acima e apague o e-mail dos outros (ou marque a data de saída '
          'de quem não é mais do projeto). Depois rode o migrate de novo.\n'
          'Nada foi alterado no banco.'
    )


def desfazer_conferencia(apps, schema_editor):
    """Nada a desfazer: a conferência só lê."""


class Migration(migrations.Migration):

    dependencies = [
        ('voluntario', '0019_alter_historicolideranca_cargo'),
    ]

    operations = [
        migrations.RunPython(conferir_antes, desfazer_conferencia),
        migrations.AddConstraint(
            model_name='voluntario',
            constraint=models.UniqueConstraint(
                Lower('email'),
                condition=models.Q(('email', ''), _negated=True),
                name='voluntario_email_unico_quando_preenchido',
                violation_error_message=(
                    'Já existe outro voluntário com este e-mail. Dois cadastros '
                    'com o mesmo e-mail impedem a entrada pelo Google.'
                ),
            ),
        ),
    ]
