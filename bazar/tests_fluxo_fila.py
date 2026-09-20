"""O fluxo da fila de ponta a ponta: buscar -> ficha -> pontos.

Escrito para responder uma pergunta concreta ("ja ta finalizado? pesquisa o
atendido e tudo mais?") com evidencia, e nao com opiniao.
"""
import datetime
import json

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase
from django.utils import timezone

from atendido.models import Atendido
from bazar.models import Bazar, Categoria

Voluntario = get_user_model()


class FluxoDaFilaTests(TestCase):

    def setUp(self):
        self.pessoa = Voluntario(username='caixa1', area='EVENTOS')
        self.pessoa.set_password('x')
        self.pessoa.save()
        self.bazar = Bazar.objects.create(
            nome='Edicao de teste', data=timezone.localdate(),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=20,
            criado_por=self.pessoa)
        Categoria.objects.create(bazar=self.bazar, nome='Camiseta', pontos=2,
                                 estoque_inicial=50, ordem=1, ativo=True)
        self.maria = Atendido.objects.create(
            nome='Maria Aparecida Souza', data_nascimento=datetime.date(2015, 4, 2),
            sala='AMARELO', ativo=True,
            numeracao_camisa='10', numeracao_calca='12', numeracao_calcado='32')
        self.inativa = Atendido.objects.create(
            nome='Joana Inativa', data_nascimento=datetime.date(2014, 1, 1),
            sala='AZUL', ativo=False)

    def _json(self, view, *args, **extras):
        pedido = RequestFactory().get('/bazar/x/', extras)
        pedido.user = self.pessoa
        pedido.session = SessionStore()
        resposta = view(pedido, *args)
        return resposta.status_code, json.loads(resposta.content)

    def test_busca_acha_pelo_pedaco_do_nome(self):
        from bazar.views import buscar_atendido

        codigo, dados = self._json(buscar_atendido, q='apareci')

        self.assertEqual(codigo, 200)
        self.assertEqual(len(dados['resultados']), 1)
        achada = dados['resultados'][0]
        self.assertEqual(achada['nome'], 'Maria Aparecida Souza')
        self.assertEqual(achada['sala'], 'Amarelo')

    def test_a_busca_ja_traz_idade_e_numeracoes(self):
        """E o que separa homonimo na fila, sem precisar de segunda tela."""
        from bazar.views import buscar_atendido

        _, dados = self._json(buscar_atendido, q='maria')
        achada = dados['resultados'][0]

        self.assertIsNotNone(achada['idade'])
        self.assertEqual(achada['numeracoes']['camisa'], '10')
        self.assertEqual(achada['numeracoes']['calcado'], '32')

    def test_atendido_inativo_nao_aparece(self):
        """`Atendido.objects.ativos()` e `filter(ativo=True)`. Quem esta
        inativo nao aparece — e a tela hoje diz "ninguem com esse nome", sem
        distinguir 'nao existe' de 'esta inativo'."""
        from bazar.views import buscar_atendido

        _, dados = self._json(buscar_atendido, q='joana')

        self.assertEqual(dados['resultados'], [])

    def test_uma_letra_so_nao_busca(self):
        from bazar.views import buscar_atendido
        _, dados = self._json(buscar_atendido, q='m')
        self.assertEqual(dados['resultados'], [])

    def test_a_ficha_traz_o_saldo_de_pontos(self):
        from bazar.views import situacao

        codigo, dados = self._json(situacao, self.maria.pk)

        self.assertEqual(codigo, 200)
        self.assertEqual(dados['nome'], 'Maria Aparecida Souza')
        self.assertEqual(dados['cota'], 20)
        self.assertEqual(dados['saldo'], 20)      # ainda nao retirou nada

    def test_sem_bazar_aberto_a_busca_responde_409(self):
        """E o 409 que a tela HOJE confunde com 'ninguem encontrado'."""
        from bazar.views import buscar_atendido

        self.bazar.etapa = Bazar.Etapa.ENCERRADO
        self.bazar.save()

        codigo, dados = self._json(buscar_atendido, q='maria')

        self.assertEqual(codigo, 409)
        self.assertIn('erro', dados)
