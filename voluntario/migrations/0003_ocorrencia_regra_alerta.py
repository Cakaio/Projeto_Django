from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('voluntario', '0002_ocorrencia'),
    ]

    operations = [
        migrations.AddField(
            model_name='ocorrencia',
            name='regra',
            field=models.CharField(blank=True, max_length=5, null=True),
        ),
        migrations.AlterField(
            model_name='ocorrencia',
            name='tipo',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('ALERTA', 'Alerta'),
                    ('ADVERTENCIA', 'Advertência'),
                    ('SUSPENSAO', 'Suspensão'),
                ],
            ),
        ),
    ]
