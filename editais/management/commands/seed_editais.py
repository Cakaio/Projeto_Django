"""Ponto de partida do robô: o dicionário de palavras-chave e algumas fontes.

Uso:
    python manage.py seed_editais

Idempotente: pode rodar de novo sem duplicar nada. Palavras que já existem não
têm o peso alterado — se o CR ajustou o peso pela tela, foi por um motivo.

As sete fontes RSS aqui foram testadas uma a uma e entram LIGADAS — o robô já
serve no primeiro dia. As reprovadas (Prosas, que bloqueia robô, e o Mapa das
OSC, que não publica os dados) ficam DESLIGADAS com o motivo no nome, para
ninguém gastar tempo redescobrindo o problema.
"""
from django.core.management.base import BaseCommand

from editais.models import ConsultaBusca, FonteEdital, PalavraChave

# Peso 3 = é a cara do PCF; 2 = combina; 1 = pode servir.
PALAVRAS_POSITIVAS = [
    ('criança', 3),
    ('infância', 3),
    ('primeira infância', 3),
    ('adolescente', 3),
    ('juventude', 2),
    ('educação', 2),
    ('contraturno', 3),
    ('socioeducativo', 3),
    ('terceiro setor', 2),
    ('OSC', 2),
    ('OSCIP', 2),
    ('sociedade civil', 2),
    ('filantropia', 2),
    ('voluntariado', 2),
    ('assistência social', 2),
    ('vulnerabilidade social', 3),
    ('esporte', 1),
    ('cultura', 1),
    ('doação', 1),
    ('incentivo fiscal', 2),
    ('FIA', 2),
    ('CMDCA', 3),
    ('comunidade', 1),
]

# Termos que aparecem em chamada de pesquisa, empresa ou pós-graduação: não é
# do que o projeto precisa, e sem eles a lista enche de ruído.
PALAVRAS_NEGATIVAS = [
    ('mestrado', -3),
    ('doutorado', -3),
    ('pós-graduação', -3),
    ('bolsa de pesquisa', -3),
    ('startup', -2),
    ('pesquisa científica', -2),
    ('inovação tecnológica', -2),
    ('exportação', -3),
]

# Fontes RSS testadas em 12/08/2026: todas responderam com itens de verdade.
# Entram LIGADAS porque foram conferidas uma a uma — o robô já funciona no
# primeiro dia, sem ninguém precisar descobrir onde procurar.
FONTES = [
    {
        'nome': 'ABCR — Editais',
        'url': 'https://captadores.org.br/category/editais/feed/',
        'tipo': 'RSS',
        'ativo': True,
    },
    {
        'nome': 'Observatório 3º Setor',
        'url': 'https://observatorio3setor.org.br/feed/',
        'tipo': 'RSS',
        'ativo': True,
    },
    {
        'nome': 'Escola Aberta do 3º Setor',
        'url': 'https://escolaaberta3setor.org.br/feed/',
        'tipo': 'RSS',
        'ativo': True,
    },
    {
        'nome': 'GIFE — institutos e fundações',
        'url': 'https://gife.org.br/feed/',
        'tipo': 'RSS',
        'ativo': True,
    },
    {
        'nome': 'Itaú Social',
        'url': 'https://www.itausocial.org.br/feed/',
        'tipo': 'RSS',
        'ativo': True,
    },
    {
        'nome': 'Instituto Tecendo Infâncias',
        'url': 'https://tecendoinfancias.org.br/feed/',
        'tipo': 'RSS',
        'ativo': True,
    },
    {
        'nome': 'Plataforma Conjunta',
        'url': 'https://conjunta.org/feed/',
        'tipo': 'RSS',
        'ativo': True,
    },
    # Conferidas e reprovadas — ficam registradas DESLIGADAS, com o motivo, para
    # ninguém perder tempo tentando de novo (e para alguém tentar outro caminho
    # se um dia quiser).
    {
        'nome': 'Prosas — a maior base de editais (BLOQUEIA ROBÔ: HTTP 403)',
        'url': 'https://prosas.com.br/editais',
        'tipo': 'HTML',
        'seletor_item': 'article',
        'seletor_titulo': 'h2, h3',
        'seletor_link': 'a',
        'seletor_descricao': 'p',
        'ativo': False,
    },
    {
        'nome': 'Mapa das OSC / IPEA (sem dados no HTML: manda para o Prosas)',
        'url': 'https://mapaosc.ipea.gov.br/editais',
        'tipo': 'HTML',
        'seletor_item': 'article',
        'seletor_titulo': 'h2, h3',
        'seletor_link': 'a',
        'seletor_descricao': 'p',
        'ativo': False,
    },
]

# As perguntas que o robô faz à web. É esta lista que encontra edital em site
# que ninguém mapeou — e ela é editável na tela, porque quem sabe o que o
# projeto precisa é o CR.
CONSULTAS = [
    'edital aberto 2026 organização da sociedade civil criança adolescente',
    'edital 2026 projeto social infância inscrições abertas OSC',
    'edital patrocínio projeto social criança contraturno 2026',
    'chamada pública 2026 terceiro setor assistência social criança',
    'edital FIA CMDCA 2026 fundo da infância e adolescência',
    'edital instituto fundação apoio projeto social infância 2026',
    'edital lei de incentivo projeto social criança 2026',
    'edital educação infantil OSC 2026 inscrições abertas',
]


class Command(BaseCommand):
    help = 'Cria as palavras-chave, as fontes conferidas e as consultas de busca.'

    def handle(self, *args, **opcoes):
        criadas = existentes = 0
        for termo, peso in PALAVRAS_POSITIVAS + PALAVRAS_NEGATIVAS:
            _, criada = PalavraChave.objects.get_or_create(
                termo=termo, defaults={'peso': peso, 'ativo': True})
            criadas += criada
            existentes += not criada

        fontes_criadas = fontes_existentes = 0
        for dados in FONTES:
            # `ativo` vem de cada fonte: as sete conferidas entram ligadas, as
            # reprovadas entram desligadas com o motivo no nome.
            _, criada = FonteEdital.objects.get_or_create(
                url=dados['url'], defaults=dict(dados),
            )
            fontes_criadas += criada
            fontes_existentes += not criada

        consultas_criadas = consultas_existentes = 0
        for termo in CONSULTAS:
            _, criada = ConsultaBusca.objects.get_or_create(
                termo=termo, defaults={'ativo': True})
            consultas_criadas += criada
            consultas_existentes += not criada

        self.stdout.write(self.style.SUCCESS(
            f'{criadas} palavra(s)-chave criada(s); {existentes} já existiam (peso preservado).'))
        self.stdout.write(self.style.SUCCESS(
            f'{fontes_criadas} fonte(s) criada(s); {fontes_existentes} já existiam.'))
        self.stdout.write(self.style.SUCCESS(
            f'{consultas_criadas} consulta(s) de busca criada(s); {consultas_existentes} já existiam.'))
        self.stdout.write(
            '\nAgora rode:\n'
            '  python manage.py buscar_editais   (lê as fontes conferidas)\n'
            '  python manage.py varrer_editais   (pergunta à web e descobre novas)')
