from django.db import migrations

def seed_locais(apps, schema_editor):
    LocalRonda = apps.get_model('ronda', 'LocalRonda')
    for ordem, nome in enumerate(['Brinquedoteca', 'Campus', 'Prédios'], start=1):
        LocalRonda.objects.get_or_create(nome=nome, defaults={'ordem': ordem, 'ativo': True})

def remover_locais(apps, schema_editor):
    LocalRonda = apps.get_model('ronda', 'LocalRonda')
    LocalRonda.objects.filter(nome__in=['Brinquedoteca', 'Campus', 'Prédios']).delete()

class Migration(migrations.Migration):
    dependencies = [('ronda', '0001_initial')]
    operations = [migrations.RunPython(seed_locais, remover_locais)]
