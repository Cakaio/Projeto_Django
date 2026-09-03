"""Cria a primeira coleção do acervo: as postulações.

Entra por migração para o acervo não abrir vazio no deploy, com uma tela de
"crie a primeira coleção" que ninguém sabe como preencher. A descrição diz o
que entra, porque acervo sem critério vira pasta de downloads.

O nome e o texto são editáveis pela tela — se a liderança quiser mudar, muda.
"""
from django.db import migrations
from django.utils.text import slugify

NOME = 'Postulações'
DESCRICAO = (
    'Documentos das postulações a cargos de liderança, ano a ano — de quem foi '
    'eleito e de quem não foi. Serve para consultar o que já foi proposto ao '
    'projeto e como cada gestão chegou onde chegou.'
)


def criar(apps, schema_editor):
    Colecao = apps.get_model('acervo', 'Colecao')
    # get_or_create e não create: a migração pode rodar num banco onde alguém já
    # cadastrou a coleção à mão pelo admin.
    Colecao.objects.get_or_create(
        slug=slugify(NOME),
        defaults={'nome': NOME, 'descricao': DESCRICAO, 'ordem': 0, 'ativo': True},
    )


def remover(apps, schema_editor):
    """Só apaga a coleção se ela ainda estiver vazia.

    Reverter a migração não é motivo para levar documento de postulação junto —
    e o PROTECT do modelo impediria de qualquer forma.
    """
    Colecao = apps.get_model('acervo', 'Colecao')
    for colecao in Colecao.objects.filter(slug=slugify(NOME)):
        if not colecao.documentos.exists():
            colecao.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('acervo', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(criar, remover),
    ]
