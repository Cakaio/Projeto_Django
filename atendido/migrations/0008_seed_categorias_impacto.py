from django.db import migrations

CATEGORIAS = [
    "Desenvolvimento Socioemocional",
    "Relacionamento e Socialização",
    "Desenvolvimento Cognitivo e Escolar",
    "Autonomia e Responsabilidade",
    "Desenvolvimento Integral da Criança",
    "Apoio às Famílias",
]


def seed(apps, schema_editor):
    Mudanca = apps.get_model("atendido", "Mudanca")
    for nome in CATEGORIAS:
        Mudanca.objects.get_or_create(mudanca=nome)
    # Remove aspectos antigos que não sejam uma das 6 categorias
    Mudanca.objects.exclude(mudanca__in=CATEGORIAS).delete()


def unseed(apps, schema_editor):
    # Não recria os aspectos antigos; apenas mantém as categorias.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("atendido", "0007_atendido_aspectos_outros"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
