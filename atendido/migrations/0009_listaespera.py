from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("atendido", "0008_seed_categorias_impacto"),
        ("voluntario", "0010_alter_voluntario_cargo"),
    ]

    operations = [
        migrations.CreateModel(
            name="ListaEspera",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome_atendido", models.CharField(help_text="Nome completo do atendido", max_length=50)),
                ("data_nascimento", models.DateField(help_text="Data de nascimento do atendido")),
                ("idade", models.PositiveSmallIntegerField(editable=False)),
                ("sala", models.CharField(choices=[("VIOLETA", "Violeta"), ("ANIL", "Anil"), ("AZUL", "Azul"), ("VERDE", "Verde"), ("AMARELO", "Amarelo"), ("LARANJA", "Laranja"), ("VERMELHO", "Vermelho"), ("FAMILIA_FELIZ", "Família Feliz")], editable=False, max_length=20)),
                ("nome_responsavel", models.CharField(help_text="Nome completo do responsável pelo atendido", max_length=50)),
                ("contato_responsavel", models.CharField(help_text="Número de contato do responsável pelo atendido, somente números", max_length=11)),
                ("renda_familiar", models.CharField(choices=[("MENOS DE 1000", "menos de 1000"), ("ENTRE 1000-1500", "Entre 1000 e 1500"), ("ENTRE 1500-2000", "Entre 1500 e 2000"), ("ENTRE 2000-3000", "Entre 2000 e 3000"), ("ENTRE 3000-4000", "Entre 3000 e 4000"), ("ENTRE 4000-5000", "Entre 4000 e 5000"), ("MAIS DE 5000", "Mais de 5000")], help_text="Renda familiar do atendido", max_length=20)),
                ("quantidade_pessoas_familia", models.IntegerField(default=1, help_text="Quantidade de pessoas na família do atendido")),
                ("parente_dentro_projeto", models.BooleanField(default=False, help_text="O atendido possui algum parente que mora junto e que já participa do Projeto Criança Feliz?")),
                ("status", models.CharField(choices=[("PENDENTE", "Pendente"), ("APROVADO", "Aprovado"), ("REPROVADO", "Reprovado")], default="PENDENTE", help_text="Status da inscrição do atendido na lista de espera", max_length=20)),
                ("observacoes", models.TextField(blank=True, help_text="Observações adicionais sobre o atendido ou a família", null=True)),
                ("data_preenchimento", models.DateTimeField(default=django.utils.timezone.now, help_text="Data de preenchimento do formulário de inscrição")),
                ("preenchido_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inscricoes_preenchidas", to="voluntario.voluntario")),
            ],
            options={
                "verbose_name": "lista de espera",
                "verbose_name_plural": "listas de espera",
                "ordering": ("sala", "data_preenchimento", "nome_atendido"),
            },
        ),
    ]
