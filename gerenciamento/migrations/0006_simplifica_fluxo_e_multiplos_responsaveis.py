from django.conf import settings
from django.db import migrations, models


def migrar_status_e_responsaveis(apps, schema_editor):
    Pauta = apps.get_model("gerenciamento", "Pauta")
    Responsabilidade = Pauta.responsaveis.through

    vinculos = [
        Responsabilidade(pauta_id=pauta_id, voluntario_id=responsavel_id)
        for pauta_id, responsavel_id in (
            Pauta.objects.exclude(responsavel_id=None)
            .values_list("pk", "responsavel_id")
        )
    ]
    Responsabilidade.objects.bulk_create(vinculos, ignore_conflicts=True)

    conversoes = {
        "AGUARDANDO_CIENCIA": "A_DISCUTIR",
        "CIENCIA_REALIZADA": "A_DISCUTIR",
        "BLOQUEADA": "A_DISCUTIR",
    }
    for antigo, novo in conversoes.items():
        Pauta.objects.filter(status=antigo).update(status=novo)

    reunioes_ids = (
        Pauta.objects.exclude(reuniao_id=None)
        .values_list("reuniao_id", flat=True)
        .distinct()
    )
    for reuniao_id in reunioes_ids:
        pautas = list(
            Pauta.objects.filter(reuniao_id=reuniao_id)
            .order_by("prazo_ddl", "pk")
        )
        for ordem, pauta in enumerate(pautas, start=1):
            pauta.ordem_reuniao = ordem
        Pauta.objects.bulk_update(pautas, ["ordem_reuniao"])


def restaurar_status_e_responsavel(apps, schema_editor):
    Pauta = apps.get_model("gerenciamento", "Pauta")
    Responsabilidade = Pauta.responsaveis.through

    Pauta.objects.filter(status="A_DISCUTIR").update(
        status="AGUARDANDO_CIENCIA"
    )
    for pauta in Pauta.objects.all().iterator():
        responsavel_id = (
            Responsabilidade.objects.filter(pauta_id=pauta.pk)
            .values_list("voluntario_id", flat=True)
            .first()
        )
        if responsavel_id:
            pauta.responsavel_id = responsavel_id
            pauta.save(update_fields=["responsavel"])


class Migration(migrations.Migration):
    dependencies = [
        ("gerenciamento", "0005_reuniao_e_kanban"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="pauta",
            name="responsaveis",
            field=models.ManyToManyField(
                blank=True,
                related_name="pautas_sob_responsabilidade",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="pauta",
            name="ordem_reuniao",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Posição da pauta no roteiro da reunião.",
            ),
        ),
        migrations.RunPython(
            migrar_status_e_responsaveis,
            restaurar_status_e_responsavel,
        ),
        migrations.RemoveField(
            model_name="pauta",
            name="responsavel",
        ),
        migrations.RemoveField(
            model_name="cienciapauta",
            name="ocultada",
        ),
        migrations.RemoveField(
            model_name="cienciapauta",
            name="ocultada_em",
        ),
        migrations.AlterField(
            model_name="pauta",
            name="status",
            field=models.CharField(
                choices=[
                    ("A_DISCUTIR", "A discutir"),
                    ("EM_DISCUSSAO", "Em discussão"),
                    ("CONCLUIDA", "Concluída"),
                ],
                default="A_DISCUTIR",
                max_length=24,
            ),
        ),
    ]
