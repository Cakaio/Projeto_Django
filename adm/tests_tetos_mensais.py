"""A tela de tetos passou a ser MENSAL — e renomear contexto é mudo.

O defeito que este arquivo existe para impedir já aconteceu nesta mesma tela:
a migration `0005` trocou `competencia` por `vigente_desde` e o template
continuou renderizando o nome antigo. Campo inexistente em template do Django
NÃO dá erro — sai string vazia. A tela ficou meses sem deixar cadastrar teto
nenhum, e a suíte não pegou.

Aqui o risco é o mesmo: `semestre_rotulo`/`semestres` viraram
`mes_rotulo`/`meses`. Se um dos nomes antigos sobreviver num template, o
seletor abre VAZIO e o cabeçalho sai sem período — sem erro nenhum.
"""
import re
from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, SimpleTestCase, TestCase

from adm import views

Voluntario = get_user_model()

NOMES_APOSENTADOS = ('semestre_rotulo', 'semestres', 'opcao.valor == semestre')


class ContextoAntigoNaoSobreviveTests(SimpleTestCase):

    def test_nenhum_template_usa_o_contexto_do_semestre(self):
        """String vazia no lugar do período é o defeito silencioso."""
        raiz = Path(settings.BASE_DIR)
        sobras = []

        for caminho in raiz.rglob('*.html'):
            if any(p in ('venv', 'node_modules', 'staticfiles', '.git')
                   for p in caminho.parts):
                continue
            texto = caminho.read_text(encoding='utf-8', errors='replace')
            for nome in NOMES_APOSENTADOS:
                if nome in texto:
                    sobras.append(f'{caminho.relative_to(raiz)}: {nome}')

        self.assertEqual(
            sobras, [],
            'Contexto aposentado ainda renderizado: {}. O Django não dá erro '
            'para variável inexistente — sai string vazia, e o seletor de mês '
            'abre em branco.'.format(sobras))


class TelaDeTetosMensalTests(TestCase):

    def setUp(self):
        self.ana = Voluntario.objects.create_user(
            username='ana', password='x', area='AMARELO')

    def _html(self, query=None):
        pedido = RequestFactory().get('/adm/tetos/', query or {})
        pedido.user = self.ana
        pedido.session = SessionStore()
        resposta = views.tetos(pedido)
        return (resposta.rendered_content if hasattr(resposta, 'rendered_content')
                else resposta.content.decode())

    def test_o_seletor_de_mes_vem_preenchido(self):
        """Doze meses, não um `<select>` vazio."""
        html = self._html()
        bloco = html[html.index('name="mes"'):]
        bloco = bloco[:bloco.index('</select>')]

        self.assertEqual(len(re.findall(r'<option ', bloco)), 12)

    def test_o_mes_escolhido_aparece_escrito_na_tela(self):
        html = self._html({'mes': '2026-09'})

        self.assertIn('setembro de 2026', html)
        self.assertNotIn('semestre', html.lower())

    def test_a_tela_diz_que_o_teto_ZERA_no_mes_seguinte(self):
        """É a regra nova e a que mais muda a expectativa de quem lê: sem
        dizer, o líder que estourou acha que ficou sem teto até o fim do ano."""
        self.assertIn('o gasto zera a cada mês', self._html())

    def test_mes_torto_na_url_nao_derruba_a_tela(self):
        """Link colado no grupo do WhatsApp não vira 500 na única tela do
        Financeiro aberta a todos."""
        for bruto in ('2026-13', 'mes passado', '2026', ''):
            with self.subTest(bruto=bruto):
                self.assertIn('Teto x gasto', self._html({'mes': bruto}))

    def test_o_periodo_mostrado_e_o_mes_inteiro(self):
        from adm.servicos import limites_do_mes

        self.assertEqual(limites_do_mes(date(2026, 9, 15)),
                         (date(2026, 9, 1), date(2026, 9, 30)))
