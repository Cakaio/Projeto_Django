"""Ponto de partida do robô: as fontes conferidas e as consultas de busca.

Uso:
    python manage.py seed_editais

As palavras-chave NÃO moram mais aqui: elas entram sozinhas pela migração
`editais/0002_dicionario_de_palavras_chave.py`, para o robô já pontuar certo no
deploy sem ninguém precisar lembrar de rodar comando. Manter as duas listas era
garantir que uma hora divergiriam.

Idempotente: pode rodar de novo sem duplicar nada.

As sete fontes RSS aqui foram testadas uma a uma e entram LIGADAS — o robô já
serve no primeiro dia. As reprovadas (Prosas, que bloqueia robô, e o Mapa das
OSC, que não publica os dados) ficam DESLIGADAS com o motivo no nome, para
ninguém gastar tempo redescobrindo o problema.
"""
from django.core.management.base import BaseCommand

from editais.models import ConsultaBusca, FonteEdital

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
    help = 'Cria as fontes conferidas e as consultas de busca do robô.'

    def handle(self, *args, **opcoes):
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
            f'{fontes_criadas} fonte(s) criada(s); {fontes_existentes} já existiam.'))
        self.stdout.write(self.style.SUCCESS(
            f'{consultas_criadas} consulta(s) de busca criada(s); {consultas_existentes} já existiam.'))
        self.stdout.write(
            '\nAgora rode:\n'
            '  python manage.py buscar_editais   (lê as fontes conferidas)\n'
            '  python manage.py varrer_editais   (pergunta à web e descobre novas)')
