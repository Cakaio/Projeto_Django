import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("voluntario", "0011_grupo"),
    ]

    operations = [
        migrations.CreateModel(
            name="Pauta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("titulo", models.CharField(max_length=180)),
                ("descricao", models.TextField()),
                ("emitido_por_area", models.CharField(choices=[("VIOLETA", "Violeta"), ("ANIL", "Anil"), ("AZUL", "Azul"), ("VERDE", "Verde"), ("AMARELO", "Amarelo"), ("LARANJA", "Laranja"), ("VERMELHO", "Vermelho"), ("FAMILIA_FELIZ", "Família Feliz"), ("MARKETING", "Marketing"), ("ADM/FIN", "Adm/Fin"), ("CR/RE", "Cr/Re"), ("EVENTOS", "Eventos"), ("GESTAO_DE_TALENTOS", "Gestão de Talentos"), ("RECREACAO", "Recreação"), ("SUPPLY", "Supply"), ("PROJETOS", "Projetos"), ("TRIADE", "Tríade")], help_text="Área do autor no momento em que a pauta foi criada.", max_length=30)),
                ("ddl", models.DateTimeField(verbose_name="prazo")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("criado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pautas_criadas", to=settings.AUTH_USER_MODEL)),
                ("grupo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pautas", to="voluntario.grupo")),
            ],
            options={"verbose_name": "Pauta", "verbose_name_plural": "Pautas", "ordering": ["ddl", "-criado_em"]},
        ),
        migrations.CreateModel(
            name="ComentarioPauta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("texto", models.TextField(max_length=2000)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("autor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="comentarios_em_pautas", to=settings.AUTH_USER_MODEL)),
                ("pauta", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comentarios", to="gerenciamento.pauta")),
            ],
            options={"verbose_name": "Comentário de pauta", "verbose_name_plural": "Comentários de pautas", "ordering": ["criado_em"]},
        ),
    ]
