"""Popula o dicionário de palavras-chave do robô.

Até aqui as palavras só nasciam pelo `manage.py seed_editais`, que alguém tinha
que lembrar de rodar. Numa migração elas entram sozinhas no deploy, que é o que
faz o robô já pontuar direito no primeiro dia.

Não altera peso de termo que já existe: se o CR ajustou pela tela, foi por um
motivo, e uma migração não tem como saber qual.

Sobre pesos: 3 = é a cara do PCF; 2 = combina; 1 = pode servir. Negativo
derruba a nota, e o robô descarta o que fica abaixo do corte (`--minimo`, 2 por
padrão).

Termo curto é perigoso aqui. A pontuação casa palavra inteira sem acento, então
uma sigla que também é palavra comum contamina tudo: 'SUAS' (o Sistema Único de
Assistência Social) casaria com o pronome "suas" em qualquer texto e daria nota
a edital nenhum a ver. Por isso ela ficou de fora, e as siglas que entraram são
as que não viram palavra comum: OSC, OSCIP, ONG, FIA, CMDCA, CRAS, CREAS, CEBAS.
"""
from django.db import migrations

# O que atrai. Inclui os termos que já vinham do seed_editais, para quem nunca
# rodou o comando também sair do zero.
POSITIVAS = [
    ('criança', 3),
    ('infância', 3),
    ('primeira infância', 3),
    ('adolescente', 3),
    ('juventude', 2),
    ('educação', 2),
    ('contraturno', 3),
    ('contraturno escolar', 3),
    ('educação integral', 3),
    ('socioeducativo', 3),
    ('terceiro setor', 2),
    ('OSC', 2),
    ('OSCIP', 2),
    ('ONG', 2),
    ('sociedade civil', 2),
    ('sem fins lucrativos', 2),
    ('filantropia', 2),
    ('voluntariado', 2),
    ('assistência social', 2),
    ('vulnerabilidade social', 3),
    ('esporte', 1),
    ('esporte educacional', 2),
    ('cultura', 1),
    ('arte-educação', 2),
    ('doação', 1),
    ('incentivo fiscal', 2),
    ('FIA', 2),
    ('CMDCA', 3),
    ('comunidade', 1),
    ('projeto social', 3),
    ('chamada pública', 2),
    ('termo de fomento', 2),
    ('termo de colaboração', 2),
    ('MROSC', 2),
    ('fomento', 1),
    ('patrocínio', 2),
    ('CEBAS', 2),
    ('utilidade pública', 2),
    ('direitos da criança', 3),
    ('estatuto da criança e do adolescente', 3),
    ('conselho tutelar', 2),
    ('protagonismo juvenil', 2),
    ('reforço escolar', 2),
    ('alfabetização', 2),
    ('letramento', 2),
    ('evasão escolar', 2),
    ('busca ativa escolar', 2),
    ('segurança alimentar', 2),
    ('saúde bucal', 1),
    ('formação de educadores', 2),
    ('capacitação de voluntários', 2),
    ('CRAS', 1),
    ('CREAS', 1),
    ('Lorena', 2),
    ('Vale do Paraíba', 3),
    ('interior de São Paulo', 2),
]

# O que descarta. São chamadas de pesquisa, de empresa e de compra pública:
# aparecem nas mesmas fontes e, sem isso, a lista do CR enche de ruído.
NEGATIVAS = [
    ('mestrado', -3),
    ('doutorado', -3),
    ('pós-graduação', -3),
    ('bolsa de pesquisa', -3),
    ('startup', -2),
    ('pesquisa científica', -2),
    ('inovação tecnológica', -2),
    ('exportação', -3),
    ('licitação', -3),
    ('pregão', -3),
    ('concurso público', -3),
    ('chamada de trabalhos', -3),
    ('artigo científico', -3),
    ('iniciação científica', -3),
    ('residência médica', -3),
    ('vestibular', -3),
    ('CAPES', -3),
    ('CNPq', -2),
    ('FAPESP', -2),
    ('incubadora', -2),
    ('aceleração de startups', -3),
    ('patente', -2),
]


def semear(apps, schema_editor):
    PalavraChave = apps.get_model('editais', 'PalavraChave')
    for termo, peso in POSITIVAS + NEGATIVAS:
        PalavraChave.objects.get_or_create(
            termo=termo,
            defaults={'peso': peso, 'ativo': True},
        )


def remover(apps, schema_editor):
    """Só apaga o que esta migração criou e ninguém mexeu depois.

    Termo com peso diferente do semeado foi ajustado por gente — reverter a
    migração não é motivo para jogar esse ajuste fora.
    """
    PalavraChave = apps.get_model('editais', 'PalavraChave')
    for termo, peso in POSITIVAS + NEGATIVAS:
        PalavraChave.objects.filter(termo=termo, peso=peso).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('editais', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(semear, remover),
    ]
