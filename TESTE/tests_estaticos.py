"""Duas linhas de configuração que quebram telas em silêncio.

Nenhuma das duas dá erro quando está errada, e é isso que as torna caras:

- App fora do `content` do Tailwind → a classe usada só nele é purgada, e a
  tela carrega sem estilo nenhum. Sem aviso, sem log, sem exceção.
- JS fora de `ARQUIVOS_OBSERVADOS` → o carimbo `?v=` não muda quando o arquivo
  muda, e quem já visitou o site continua recebendo a versão antiga. O
  docstring de `TESTE/versao_estatica.py` registra que isso já custou três
  rodadas de confusão.

Só um teste pega. Por isso este arquivo existe.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from TESTE.versao_estatica import ARQUIVOS_OBSERVADOS

# Todo diretório do projeto que guarda template. Acrescente o app novo aqui na
# mesma hora em que criar o primeiro template dele.
APPS_COM_TEMPLATE = [
    'templates', 'atendido', 'voluntario', 'semanario', 'sabado', 'supply',
    'adm', 'forms_pcf', 'ronda', 'gerenciamento', 'parceiros', 'editais',
    'revista', 'projetos', 'acervo', 'bazar', 'estudio', 'notificacoes',
]

IGNORAR_NA_VARREDURA = ('venv', 'node_modules', 'staticfiles', '.git')


class ConteudoDoTailwindTest(SimpleTestCase):
    """Classe usada SÓ num app fora do `content` é purgada sem erro nenhum."""

    def test_todo_app_com_template_esta_no_content(self):
        config = (Path(settings.BASE_DIR) / 'tailwindcss' / 'tailwind.config.js'
                  ).read_text(encoding='utf-8')
        inicio = config.index('content:')
        bloco = config[inicio:config.index(']', inicio)]

        faltando = [app for app in APPS_COM_TEMPLATE if f'/{app}/' not in bloco]

        self.assertEqual(
            faltando, [],
            f'Apps fora do content do Tailwind: {faltando}. '
            'Classe usada só neles some do CSS, sem erro nenhum.')


class CarimboDeVersaoTest(SimpleTestCase):
    """JS fora de ARQUIVOS_OBSERVADOS não muda o `?v=`: o navegador serve o velho."""

    def test_todo_js_referenciado_em_template_e_observado(self):
        raiz = Path(settings.BASE_DIR)
        referenciados = set()

        for caminho in raiz.rglob('*.html'):
            if any(parte in IGNORAR_NA_VARREDURA for parte in caminho.parts):
                continue
            texto = caminho.read_text(encoding='utf-8', errors='replace')
            # {% static 'js/alguma-coisa.js' %} — com aspas simples ou duplas.
            for achado in re.findall(r"""static\s+['"](js/[^'"]+\.js)['"]""", texto):
                referenciados.add(achado)

        faltando = sorted(referenciados - set(ARQUIVOS_OBSERVADOS))

        self.assertEqual(
            faltando, [],
            f'JS referenciado em template e fora de ARQUIVOS_OBSERVADOS: '
            f'{faltando}. Publicar uma correção nesses arquivos não entrega '
            'nada a quem já abriu o site.')
