import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrar_status_legados(apps, schema_editor):
    Pauta = apps.get_model("gerenciamento", "Pauta")
    conversoes = {
        "A_FAZER": "AGUARDANDO_CIENCIA",
        "EM_EXECUCAO": "EM_DISCUSSAO",
        "FINALIZADA": "CONCLUIDA",
    }
    for antigo, novo in conversoes.items():
        Pauta.objects.filter(status=antigo).update(status=novo)


def restaurar_status_legados(apps, schema_editor):
    Pauta = apps.get_model("gerenciamento", "Pauta")
    conversoes = {
        "AGUARDANDO_CIENCIA": "A_FAZER",
        "CIENCIA_REALIZADA": "A_FAZER",
        "EM_DISCUSSAO": "EM_EXECUCAO",
        "CONCLUIDA": "FINALIZADA",
    }
    for novo, antigo in conversoes.items():
        Pauta.objects.filter(status=novo).update(status=antigo)


class Migration(migrations.Migration):
    dependencies = [
        ("gerenciamento", "0004_alter_pauta_emitido_por_area"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Reuniao",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("titulo", models.CharField(max_length=180)),
                ("data_reuniao", models.DateTimeField(db_index=True)),
                ("descricao", models.TextField(blank=True)),
                (
                    "grupo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reunioes",
                        to="voluntario.grupo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Reunião",
                "verbose_name_plural": "Reuniões",
                "ordering": ["-data_reuniao", "titulo"],
            },
        ),
        migrations.RenameField(
            model_name="pauta",
            old_name="ddl",
            new_name="prazo_ddl",
        ),
        migrations.AddField(
            model_name="comentariopauta",
            name="mencoes",
            field=models.ManyToManyField(
                blank=True,
                related_name="mencoes_em_comentarios",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="pauta",
            name="etiquetas",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Lista de etiquetas curtas exibidas no card.",
            ),
        ),
        migrations.AddField(
            model_name="pauta",
            name="ordem",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Posição do card dentro da coluna Kanban.",
            ),
        ),
        migrations.AddField(
            model_name="pauta",
            name="prioridade",
            field=models.CharField(
                choices=[("BAIXA", "Baixa"), ("MEDIA", "Média"), ("ALTA", "Alta")],
                default="MEDIA",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="pauta",
            name="responsavel",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pautas_sob_responsabilidade",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="pauta",
            name="reuniao",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pautas",
                to="gerenciamento.reuniao",
            ),
        ),
        migrations.AddField(
            model_name="pauta",
            name="usuarios_ciencia",
            field=models.ManyToManyField(
                blank=True,
                related_name="pautas_com_ciencia",
                through="gerenciamento.CienciaPauta",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(migrar_status_legados, restaurar_status_legados),
        migrations.AlterField(
            model_name="pauta",
            name="prazo_ddl",
            field=models.DateTimeField(verbose_name="prazo limite"),
        ),
        migrations.AlterField(
            model_name="pauta",
            name="status",
            field=models.CharField(
                choices=[
                    ("AGUARDANDO_CIENCIA", "Aguardando ciência"),
                    ("CIENCIA_REALIZADA", "Ciência realizada"),
                    ("EM_DISCUSSAO", "Em discussão"),
                    ("BLOQUEADA", "Bloqueada"),
                    ("CONCLUIDA", "Concluída"),
                ],
                default="AGUARDANDO_CIENCIA",
                max_length=24,
            ),
        ),
        migrations.AlterModelOptions(
            name="pauta",
            options={
                "ordering": ["status", "ordem", "prazo_ddl", "-criado_em"],
                "verbose_name": "Pauta",
                "verbose_name_plural": "Pautas",
            },
        ),
    ]
