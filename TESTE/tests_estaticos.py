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


class ColetaDesatualizadaTest(SimpleTestCase):
    """O `collectstatic` esquecido quebra tela em silêncio, e já quebrou.

    Em produção quem serve `/static/` é o WhiteNoise, a partir de STATIC_ROOT —
    não do código-fonte. E ele casa pelo CAMINHO, ignorando o `?v=`. Resultado
    de um deploy sem `collectstatic`: template novo e JavaScript velho, servidos
    juntos, sem erro nenhum. Foi exatamente o que aconteceu com a tela do Bazar.
    """

    def _rodar(self, raiz_coleta):
        from TESTE.checks import coleta_de_estaticos_esta_atualizada
        return coleta_de_estaticos_esta_atualizada(
            app_configs=None, static_root=raiz_coleta)

    def test_sem_static_root_nao_reclama(self):
        """Máquina de desenvolvimento nunca rodou collectstatic, e não precisa:
        reclamar aqui seria barulho em todo `manage.py` do dia."""
        import tempfile
        from pathlib import Path
        inexistente = Path(tempfile.gettempdir()) / 'pcf-coleta-que-nao-existe'
        self.assertEqual(self._rodar(inexistente), [])

    def test_copia_mais_velha_que_a_fonte_e_denunciada(self):
        import os
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            coleta = Path(pasta) / 'staticfiles'
            (coleta / 'js').mkdir(parents=True)
            # Todas em dia, MENOS uma: é o caso real de um deploy que
            # coletou uma vez e depois esqueceu.
            for observado in ARQUIVOS_OBSERVADOS:
                destino = coleta / observado
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text('ok', encoding='utf-8')
                os.utime(destino, None)

            copia = coleta / 'js' / 'pcf-combo.js'
            fonte = Path(settings.BASE_DIR) / 'static' / 'js' / 'pcf-combo.js'
            os.utime(copia, (os.path.getmtime(fonte) - 600,) * 2)

            avisos = self._rodar(coleta)

        self.assertEqual(len(avisos), 1, avisos)
        self.assertIn('pcf-combo.js', avisos[0].msg)
        # Só a atrasada é denunciada; as em dia não viram barulho.
        self.assertNotIn('pcf-fx.js', avisos[0].msg)
        self.assertIn('collectstatic', avisos[0].hint)

    def test_copia_em_dia_nao_reclama(self):
        import os
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            coleta = Path(pasta) / 'staticfiles'
            (coleta / 'js').mkdir(parents=True)
            for observado in ARQUIVOS_OBSERVADOS:
                destino = coleta / observado
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text('novo', encoding='utf-8')
                os.utime(destino, None)   # agora

            self.assertEqual(self._rodar(coleta), [])

    def test_arquivo_que_nunca_foi_coletado_e_denunciado(self):
        """Arquivo novo entra no repositório e o deploy esquece o collectstatic:
        o navegador recebe 404 e a tela perde o comportamento inteiro."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            coleta = Path(pasta) / 'staticfiles'
            coleta.mkdir(parents=True)     # existe, mas está vazia
            avisos = self._rodar(coleta)

        self.assertTrue(avisos)
        self.assertIn('nunca coletado', avisos[0].msg)
        self.assertIn('collectstatic', avisos[0].hint)
