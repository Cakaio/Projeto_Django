"""O painel do combo tem de ficar ACIMA de todo modal do projeto.

`pcf-combo.js` anexa o painel da busca ao `document.body`, e nao ao campo que
o abriu. Isso e de proposito: dentro de um `<td>` ou de um cartao com
`overflow:hidden` a lista seria cortada. O preco e que o painel NAO HERDA o
empilhamento de quem o abriu — so o `z-index` decide quem fica na frente.

Em 09/2026 ele estava em 200 e TODO modal do projeto ficava na frente dele:
9999 no de ocorrencias e na base, 1100 no semanario, 1090 no supply, 1080 nas
pautas. A pessoa abria "Selecione a regra..." dentro do modal de Aplicar
Ocorrencias e a lista aparecia ATRAS — impossivel escolher, e sem erro nenhum.

Enquanto esta aberto, o painel E a coisa com que a pessoa esta interagindo.
Ele precisa ser o topo, sempre. Este teste existe para o numero nao virar
mentira quando alguem criar um modal novo com `z-index` maior.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

IGNORAR = ('venv', 'node_modules', 'staticfiles', '.git',
           # Vendorizado do admin do Django: nao e nosso e nao convive com o
           # combo (o admin usa o select2 dele).
           'admin')

PADRAO = re.compile(r'z-index:\s*(\d+)')


def z_index_do_painel():
    """O valor na FONTE (`input.css`), que e de onde o CSS servido nasce."""
    fonte = (Path(settings.BASE_DIR) / 'tailwindcss' / 'input.css'
             ).read_text(encoding='utf-8')
    bloco = fonte[fonte.index('.pcf-combo-painel {'):]
    return int(PADRAO.search(bloco).group(1))


def z_indexes_do_projeto():
    """Todo `z-index` declarado em template ou CSS nosso, com onde ele esta."""
    raiz = Path(settings.BASE_DIR)
    achados = []

    for extensao in ('*.html', '*.css'):
        for caminho in raiz.rglob(extensao):
            if any(parte in IGNORAR for parte in caminho.parts):
                continue
            # O `pcf.css` e GERADO a partir do input.css: conferir os dois
            # contaria o mesmo valor duas vezes.
            if caminho.name == 'pcf.css':
                continue
            texto = caminho.read_text(encoding='utf-8', errors='replace')
            for achado in PADRAO.finditer(texto):
                linha = texto[:achado.start()].count('\n') + 1
                achados.append((int(achado.group(1)),
                                f'{caminho.relative_to(raiz)}:{linha}'))
    return achados


class PainelDoComboFicaNoTopoTests(SimpleTestCase):

    def test_nenhum_z_index_do_projeto_alcanca_o_painel(self):
        painel = z_index_do_painel()

        acima = [(valor, onde) for valor, onde in z_indexes_do_projeto()
                 if valor >= painel and 'input.css' not in onde]

        self.assertEqual(
            acima, [],
            f'O painel do combo está em z-index {painel} e estes ficariam na '
            f'frente dele: {acima}. Quando isso acontece, a lista de busca '
            'abre ATRÁS do modal e não dá para escolher nada — sem erro '
            'nenhum na tela. Suba o `.pcf-combo-painel` em '
            '`tailwindcss/input.css` (e rode `npm run build`) ou baixe o '
            'outro.')

    def test_o_css_SERVIDO_carrega_o_mesmo_valor(self):
        """`input.css` é fonte; quem chega no navegador é o `pcf.css`
        compilado. Mudar a fonte e esquecer o `npm run build` deixaria o
        conserto só no repositório."""
        servido = (Path(settings.BASE_DIR) / 'static' / 'css' / 'pcf.css'
                   ).read_text(encoding='utf-8', errors='replace')
        bloco = re.search(r'pcf-combo-painel\{([^}]*)\}', servido)

        self.assertIsNotNone(bloco, 'O `.pcf-combo-painel` sumiu do CSS servido.')
        self.assertEqual(
            int(PADRAO.search(bloco.group(1)).group(1)), z_index_do_painel(),
            'O `pcf.css` servido está com outro z-index que o `input.css`. '
            'Rode `cd tailwindcss && npm run build`.')
