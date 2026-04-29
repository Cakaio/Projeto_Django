from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('voluntario', '0004_ocorrencia_deleted_at_ocorrencia_deleted_by_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Regra',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(help_text='Código curto, ex: AL1, AD2, PO1', max_length=10, unique=True)),
                ('descricao', models.TextField(help_text='Descrição completa exibida no painel e nos emails')),
                ('tipo', models.CharField(choices=[('ALERTA', 'Alerta'), ('ADVERTENCIA', 'Advertência'), ('SUSPENSAO', 'Suspensão')], max_length=20)),
                ('ativo', models.BooleanField(default=True, help_text='Disponível para aplicação no painel')),
                ('ordem', models.PositiveSmallIntegerField(default=0, help_text='Ordem de exibição dentro do grupo')),
            ],
            options={
                'verbose_name': 'Regra',
                'verbose_name_plural': 'Regras',
                'ordering': ['tipo', 'ordem', 'codigo'],
            },
        ),
    ]
