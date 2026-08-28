from django.db import migrations, models


def campus_em_trios(apps, schema_editor):
    LocalRonda = apps.get_model('ronda', 'LocalRonda')
    LocalRonda.objects.filter(nome__iexact='Campus').update(pessoas_por_grupo=3)


def campus_em_duplas(apps, schema_editor):
    LocalRonda = apps.get_model('ronda', 'LocalRonda')
    LocalRonda.objects.filter(nome__iexact='Campus').update(pessoas_por_grupo=2)


class Migration(migrations.Migration):

    dependencies = [
        ('ronda', '0004_configuracaorondasabado_dia_de_evento_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='localronda',
            name='pessoas_por_grupo',
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text='Tamanho de cada grupo do rodízio (2 = duplas, 3 = trios). '
                          'Em dia de evento o local recebe 2 grupos desse tamanho.',
                verbose_name='Pessoas por grupo',
            ),
        ),
        migrations.AlterField(
            model_name='configuracaorondasabado',
            name='dia_de_evento',
            field=models.BooleanField(
                default=False,
                help_text='Ronda rotativa: 2 grupos fixos por local (tamanho definido em cada local), sem horários.',
            ),
        ),
        migrations.AlterField(
            model_name='escalaronda',
            name='dupla',
            field=models.PositiveSmallIntegerField(
                blank=True, help_text='Grupo fixo (1 ou 2) no modo dia de evento.', null=True,
            ),
        ),
        migrations.RunPython(campus_em_trios, campus_em_duplas),
    ]
