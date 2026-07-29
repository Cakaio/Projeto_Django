from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("voluntario", "0010_alter_voluntario_cargo"),
    ]

    operations = [
        migrations.CreateModel(
            name="Grupo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=100, unique=True)),
                ("regras", models.JSONField(default=list)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Grupo",
                "verbose_name_plural": "Grupos",
                "ordering": ["nome"],
            },
        ),
    ]
