from django.db import migrations, models
import django.db.models.deletion


def ligar_materiais_a_itens(apps, schema_editor):
    Item = apps.get_model("supply", "Item")
    Material = apps.get_model("semanario", "Material")
    itens = {item.nome.strip().casefold(): item for item in Item.objects.all() if item.nome.strip()}
    for material in Material.objects.all().iterator():
        nome = (material.nome or "").strip()
        chave = nome.casefold()
        item = itens.get(chave)
        if item is None:
            item = Item.objects.create(nome=nome or "Item sem nome", unidade=material.unidade or "UN")
            itens[chave] = item
        material.item_id = item.pk
        material.save(update_fields=["item"])


class Migration(migrations.Migration):
    dependencies = [("semanario", "0005_material_link"), ("supply", "0006_pedido_item")]
    operations = [
        migrations.AddField(
            model_name="material",
            name="item",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="materiais", to="supply.item"),
        ),
        migrations.RunPython(ligar_materiais_a_itens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="material",
            name="item",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="materiais", to="supply.item"),
        ),
    ]
