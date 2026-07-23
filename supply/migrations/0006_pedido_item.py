from django.db import migrations, models
import django.db.models.deletion


def ligar_pedidos_a_itens(apps, schema_editor):
    Item = apps.get_model("supply", "Item")
    Pedido = apps.get_model("supply", "Pedido")
    itens = {item.nome.strip().casefold(): item for item in Item.objects.all() if item.nome.strip()}
    for pedido in Pedido.objects.all().iterator():
        nome = (pedido.nome or "").strip()
        chave = nome.casefold()
        item = itens.get(chave)
        if item is None:
            item = Item.objects.create(nome=nome or "Item sem nome", unidade=pedido.unidade or "UN")
            itens[chave] = item
        pedido.item_id = item.pk
        pedido.save(update_fields=["item"])


class Migration(migrations.Migration):
    dependencies = [("supply", "0005_pedido_link")]
    operations = [
        migrations.AddField(
            model_name="pedido",
            name="item",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="pedidos", to="supply.item"),
        ),
        migrations.RunPython(ligar_pedidos_a_itens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pedido",
            name="item",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="pedidos", to="supply.item"),
        ),
    ]
