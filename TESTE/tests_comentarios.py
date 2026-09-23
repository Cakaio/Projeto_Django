"""Comentario de template que NAO e comentario.

Duas formas de escrever uma nota num template do Django, e as duas tem uma
armadilha que nao da erro nenhum — a nota simplesmente APARECE NA TELA para o
voluntario, no meio do conteudo:

1. `{# ... #}` e de UMA LINHA SO. Atravessou linha, deixa de ser comentario e
   vira texto. Aconteceu em 09/2026 em seis lugares de uma vez: a tela de
   tetos e o painel do Financeiro mostravam a explicacao do codigo para quem
   abria a pagina.

2. Tag de template dentro de COMENTARIO HTML (`<!-- ... -->`) e executada
   normalmente: o Django nao sabe o que e comentario de HTML. Um `{% if %}`
   citado numa nota abre um bloco DE VERDADE, e a tela para de renderizar.
   Tambem aconteceu, escrevendo o conserto da folha do caixa do Bazar.

Para nota de varias linhas existe `{% comment %}...{% endcomment %}`, que e a
unica forma que o Django trata como bloco.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

IGNORAR = ('venv', 'node_modules', 'staticfiles', '.git', 'migrations')

# As tags que, citadas dentro de um comentario HTML, ABREM bloco de verdade.
TAGS_QUE_ABREM = ('if', 'for', 'block', 'with', 'comment', 'ifchanged',
                  'spaceless', 'autoescape', 'filter', 'verbatim')


def templates_do_projeto():
    raiz = Path(settings.BASE_DIR)
    for caminho in raiz.rglob('*.html'):
        if any(parte in IGNORAR for parte in caminho.parts):
            continue
        yield caminho, caminho.read_text(encoding='utf-8', errors='replace')


class ComentarioDeUmaLinhaTests(SimpleTestCase):

    def test_nenhum_comentario_de_cerquilha_atravessa_linha(self):
        """`{# ... #}` em varias linhas VAZA para a tela do voluntario."""
        vazando = []

        for caminho, texto in templates_do_projeto():
            for numero, linha in enumerate(texto.splitlines(), 1):
                if '{#' not in linha:
                    continue
                depois = linha.split('{#', 1)[1]
                if '#}' not in depois:
                    vazando.append(
                        f'{caminho.relative_to(settings.BASE_DIR)}:{numero}')

        self.assertEqual(
            vazando, [],
            'Comentário `{# #}` de várias linhas NÃO é comentário: o Django só '
            'reconhece a forma de uma linha, e o texto aparece na tela. '
            f'Use `{{% comment %}}` nestes lugares: {vazando}')


class TagDentroDeComentarioHtmlTests(SimpleTestCase):

    def test_nenhuma_tag_que_abre_bloco_dentro_de_comentario_html(self):
        """Comentário de HTML não esconde tag do Django — ela EXECUTA.

        Citar `{% if %}` numa nota dentro de `<!-- -->` abre um bloco de
        verdade e a tela para de renderizar com `Invalid block tag`.
        """
        problemas = []
        padrao_html = re.compile(r'<!--(.*?)-->', re.S)
        padrao_tag = re.compile(r'\{%\s*(\w+)')

        for caminho, texto in templates_do_projeto():
            for achado in padrao_html.finditer(texto):
                for tag in padrao_tag.findall(achado.group(1)):
                    if tag in TAGS_QUE_ABREM:
                        linha = texto[:achado.start()].count('\n') + 1
                        problemas.append(
                            f'{caminho.relative_to(settings.BASE_DIR)}:{linha} '
                            f'({{% {tag} %}})')

        self.assertEqual(
            problemas, [],
            'Tag do Django dentro de comentário HTML É EXECUTADA: ela abre um '
            'bloco de verdade e derruba a renderização da tela. '
            f'Tire a tag da nota ou use `{{% comment %}}`: {problemas}')


# NAO HA teste para `{% comment %}` aninhado, e a ausencia e deliberada.
# Conferido no proprio Django:
#   - tag de ABERTURA citada dentro da nota -> consumida como texto, inofensiva
#   - tag de FECHAMENTO citada dentro -> TemplateSyntaxError, erro ALTO
# Os dois testes acima existem porque aqueles defeitos sao SILENCIOSOS: a tela
# renderiza e o texto aparece. Este nao e — ele derruba a tela com o erro
# escrito, e qualquer renderizacao ja o denuncia.
