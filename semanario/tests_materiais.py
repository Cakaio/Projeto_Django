"""O modal de materiais nao pode morrer por causa do NOME de um item.

Em 09/2026 clicar em "Materiais" no semanario nao fazia absolutamente nada.
A tela montava cada `<option>` interpolando `{{ item.nome|escapejs }}` DENTRO
de uma template string de JavaScript. `escapejs` protege aspas, `<`, `>` e ate
a crase — mas NAO protege `${`. Um item chamado "Tinta ${cor}" virava
interpolacao, `novaLinhaMaterial` estourava com ReferenceError, e o modal
simplesmente nao abria: sem erro na tela, sem pista nenhuma.
"""
import json
import re

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from supply.models import Item

Voluntario = get_user_model()

# Tudo que um nome de material pode conter e que ja quebrou, ou quebraria,
# uma string de JavaScript montada na mao.
NOMES_HOSTIS = [
    'Papel A4',
    'Tinta ${cor}',              # interpolacao — foi ESTE que derrubou a tela
    'Cola `bastao`',             # crase fecha a template string
    'Lapis "preto"',
    "Fita d'agua",
    'Cartolina <azul>',
    'Massinha </script>',        # fecharia a propria tag
    'Barbante \ nylon',
]


class ModalDeMateriaisTests(TestCase):

    def setUp(self):
        self.pessoa = Voluntario(username='t', area='TRIADE',
                                 is_superuser=True, is_staff=True)
        self.pessoa.set_password('x')
        self.pessoa.save()
        for nome in NOMES_HOSTIS:
            Item.objects.create(nome=nome, unidade='UN', ativo=True)

    def _html(self):
        from semanario.views import criar_semanario

        pedido = RequestFactory().get('/semanario/novo/')
        pedido.user = self.pessoa
        pedido.session = SessionStore()
        resposta = criar_semanario(pedido)
        return (resposta.rendered_content if hasattr(resposta, 'rendered_content')
                else resposta.content.decode())

    def test_nenhum_nome_de_item_vira_javascript(self):
        """A trava de verdade: o catalogo sai por `json_script`, e nao ha mais
        NENHUM nome de item costurado no meio do codigo."""
        html = self._html()

        # `json_script` poe o catalogo numa tag propria, com type="application/json".
        self.assertIn('id="dados-itens"', html)

        codigo = ' '.join(re.findall(r'<script>(.*?)</script>', html, re.S))
        for nome in NOMES_HOSTIS:
            self.assertNotIn(nome, codigo,
                             f'O nome {nome!r} vazou para dentro do JavaScript.')

    def test_o_catalogo_chega_inteiro_e_correto(self):
        html = self._html()
        bruto = re.search(
            r'id="dados-itens"[^>]*>(.*?)</script>', html, re.S).group(1)

        catalogo = json.loads(bruto)

        self.assertEqual(sorted(i['nome'] for i in catalogo),
                         sorted(NOMES_HOSTIS))
        self.assertTrue(all(i['unidade'] for i in catalogo))

    def test_o_script_chega_inteiro_ao_navegador(self):
        """Um `</script>` solto DENTRO do bloco — ate num comentario — encerra
        a tag ali mesmo, e todo o resto vira texto na pagina. O clique entao
        chama uma funcao que nunca foi definida, e nao acontece nada.

        Nao e hipotese: aconteceu escrevendo o conserto deste arquivo.
        """
        html = self._html()
        blocos = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
        com_a_funcao = [b for b in blocos if 'function abrirMateriais' in b]

        self.assertEqual(
            len(com_a_funcao), 1,
            'O bloco que define abrirMateriais foi cortado antes da hora — '
            'procure um `</script>` dentro do proprio script.')
        # E o bloco precisa chegar ate o fim, com a ultima funcao dentro dele.
        self.assertIn('salvarMateriais', com_a_funcao[0])

    def test_a_falha_do_modal_nao_e_mais_calada(self):
        """Foi o que transformou um bug de 10 segundos numa caçada: o clique
        nao fazia nada e a tela nao dizia por que."""
        html = self._html()
        self.assertIn('avisarFalha', html)
        # O `abrirMateriais` precisa estar protegido, nao so a funcao existir.
        trecho = html[html.index('function abrirMateriais'):]
        trecho = trecho[:trecho.index('function atualizarUnidadeMaterial')]
        self.assertIn('catch', trecho)
        self.assertIn('avisarFalha', trecho)
