import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('voluntario', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Ocorrencia',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('tipo', models.CharField(choices=[('ADVERTENCIA', 'Advertência'), ('SUSPENSAO', 'Suspensão')], max_length=20)),
                ('razao', models.TextField(blank=True, null=True)),
                ('automatico', models.BooleanField(default=False, help_text='True se a suspensão foi gerada automaticamente por 3 advertências')),
                ('criado_em', models.DateTimeField(default=django.utils.timezone.now)),
                ('advertido', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='ocorrencias_recebidas',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('aplicado_por', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ocorrencias_aplicadas',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-criado_em'],
            },
        ),
    ]
