"""Cadastra a AL18 no catálogo de regras.

Até aqui a AL18 só existia na lista fixa do código: as ocorrências saíam com o
código certo, mas a regra não aparecia no painel nem no admin, e o e-mail tinha
que cair no texto embutido para descobrir a descrição. Agora ela é uma regra
como qualquer outra — a Tríade edita o texto pelo admin, e a liderança também
pode aplicá-la à mão quando o caso for esse.

`ativo=True` é o que a coloca na lista do painel (a consulta do formulário
filtra por ele). `ordem=18` a deixa logo depois da AL17, no fim dos alertas.
"""
from django.db import migrations

CODIGO = 'AL18'
DESCRICAO = 'Faltou a três sábados seguidos sem justificativa'


def cadastrar(apps, schema_editor):
    Regra = apps.get_model('voluntario', 'Regra')
    # update_or_create e não get_or_create: se alguém já tiver criado uma AL18
    # na mão pelo admin, o texto passa a ser o mesmo que o sistema usa, em vez
    # de ficarem dois textos para o mesmo código.
    Regra.objects.update_or_create(
        codigo=CODIGO,
        defaults={'descricao': DESCRICAO, 'tipo': 'ALERTA', 'ordem': 18, 'ativo': True},
    )


def descadastrar(apps, schema_editor):
    Regra = apps.get_model('voluntario', 'Regra')
    Regra.objects.filter(codigo=CODIGO).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('voluntario', '0015_alerta_de_falta_com_a_regra_certa'),
    ]

    operations = [
        migrations.RunPython(cadastrar, descadastrar),
    ]
