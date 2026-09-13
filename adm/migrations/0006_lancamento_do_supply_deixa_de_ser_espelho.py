"""O lançamento deixa de morrer junto com o pedido do Supply.

O espelho automático do Supply foi desligado (ver `adm/signals.py`). Os
lançamentos que ele criou continuam no banco e agora são registro do ADM.
Com CASCADE, apagar um pedido antigo no Supply apagaria dinheiro do
Financeiro — e o teto da área mudaria sozinho, sem ninguém saber por quê.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('supply', '0009_alter_item_categoria'),
        ('adm', '0005_teto_por_semestre'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lancamento',
            name='pedido',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lancamento', to='supply.pedido'),
        ),
    ]
