import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gerenciamento", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="pauta",
            name="status",
            field=models.CharField(
                choices=[
                    ("A_FAZER", "A fazer"),
                    ("EM_EXECUCAO", "Em execução"),
                    ("BLOQUEADA", "Bloqueada"),
                    ("FINALIZADA", "Finalizada"),
                ],
                default="A_FAZER",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="CienciaPauta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ciente_em", models.DateTimeField(auto_now_add=True)),
                ("ocultada", models.BooleanField(default=False)),
                ("ocultada_em", models.DateTimeField(blank=True, null=True)),
                ("pauta", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ciencias", to="gerenciamento.pauta")),
                ("voluntario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ciencias_de_pautas", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Ciência de pauta",
                "verbose_name_plural": "Ciências de pautas",
            },
        ),
        migrations.AddConstraint(
            model_name="cienciapauta",
            constraint=models.UniqueConstraint(fields=("pauta", "voluntario"), name="ciencia_unica_por_voluntario_e_pauta"),
        ),
    ]
