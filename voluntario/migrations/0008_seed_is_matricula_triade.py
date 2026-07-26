from django.db import migrations


def seed(apps, schema_editor):
    Voluntario = apps.get_model("voluntario", "Voluntario")
    Voluntario.objects.filter(area="TRIADE").update(is_matricula=True)


def unseed(apps, schema_editor):
    Voluntario = apps.get_model("voluntario", "Voluntario")
    Voluntario.objects.filter(area="TRIADE").update(is_matricula=False)


class Migration(migrations.Migration):

    dependencies = [
        ("voluntario", "0007_voluntario_is_matricula"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
