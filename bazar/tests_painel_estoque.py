"""O cartao "Estoque por categoria" precisa dizer o que sabe E o que nao sabe.

Antes ele era uma tabela de quatro colunas. Sem estoque inicial cadastrado —
que era o caso real no dia do evento — tres delas viravam TRAVESSAO por linha,
e a coordenacao lia um cartao que nao dizia nada e parecia quebrado. O
travessao estava tecnicamente certo (`restante` devolve None de proposito para
categoria sem controle de estoque); o que faltava era a tela EXPLICAR.
"""
import datetime

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase
from django.utils import timezone

from atendido.models import Atendido
from bazar.models import Bazar, Categoria, Retirada, SalaDoBazar

Voluntario = get_user_model()


class PainelDoEstoqueTests(TestCase):

    def setUp(self):
        self.coord = Voluntario.objects.create_user(
            username='eventos', password='x', area='EVENTOS')
        self.bazar = Bazar.objects.create(
            nome='Edicao', data=timezone.localdate(),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=20,
            criado_por=self.coord)

    def _html(self):
        from bazar.views import painel

        pedido = RequestFactory().get('/bazar/painel/')
        pedido.user = self.coord
        pedido.session = SessionStore()
        resposta = painel(pedido)
        return (resposta.rendered_content if hasattr(resposta, 'rendered_content')
                else resposta.content.decode())

    def _categoria(self, nome, pontos=2, estoque=0, ordem=1):
        return Categoria.objects.create(
            bazar=self.bazar, nome=nome, pontos=pontos,
            estoque_inicial=estoque, ordem=ordem, ativo=True)

    # ── o estado que estava no ar ────────────────────────────────────────
    def test_sem_estoque_cadastrado_a_tela_EXPLICA(self):
        """Nao basta o travessao: a tela precisa dizer por que nao sabe, e
        oferecer o caminho."""
        self._categoria('Blusas')

        html = self._html()

        self.assertIn('O estoque inicial não foi cadastrado', html)
        self.assertIn('Cadastrar agora', html)

    def test_sem_estoque_nao_promete_o_que_nao_sabe(self):
        """"restam X de Y" so aparece para quem tem estoque cadastrado."""
        self._categoria('Blusas')

        self.assertNotIn('restam', self._html())

    # ── o estado com estoque ─────────────────────────────────────────────
    def test_com_estoque_mostra_quanto_resta(self):
        self._categoria('Blusas', estoque=50)

        html = self._html()

        self.assertIn('restam 50 de 50', html)
        self.assertNotIn('O estoque inicial não foi cadastrado', html)

    def test_o_que_saiu_desconta_do_que_resta(self):
        categoria = self._categoria('Blusas', estoque=50)
        crianca = Atendido.objects.create(
            nome='Maria', data_nascimento=datetime.date(2015, 1, 1),
            sala='AMARELO', ativo=True)
        retirada = Retirada.objects.create(
            bazar=self.bazar, atendido=crianca, etapa=Retirada.Etapa.PRIMEIRA,
            conferido_por=self.coord, finalizada_em=timezone.now())
        retirada.itens.create(categoria=categoria, quantidade=4,
                              pontos_unitarios=2, pontos_total=8)

        self.assertIn('restam 46 de 50', self._html())

    # ── cadastro incompleto ──────────────────────────────────────────────
    def test_categoria_sem_nome_nao_vira_linha_fantasma(self):
        """No print do evento havia uma linha em branco: parecia defeito de
        renderizacao, e era cadastro incompleto."""
        self._categoria('   ')

        self.assertIn('(sem nome)', self._html())

    def test_sem_categoria_nenhuma_a_tela_diz_o_que_falta(self):
        html = self._html()

        self.assertIn('Nenhuma categoria cadastrada', html)

    # ── o que a lista substituiu ─────────────────────────────────────────
    def test_o_cartao_nao_rola_mais_de_lado(self):
        """A tabela tinha `min-width` maior que o cartao: barra de rolagem
        horizontal em qualquer tela, para quatro numeros curtos."""
        self._categoria('Blusas', estoque=50)

        html = self._html()
        trecho = html[html.index('Estoque por categoria'):]
        trecho = trecho[:trecho.index('</section>')]

        self.assertNotIn('min-width', trecho)
        self.assertNotIn('pcf-scroll-x', trecho)

    def test_a_barra_nao_divide_por_zero_sem_atendimento(self):
        """Bazar recem-aberto tem tudo zerado; a tela nao pode estourar."""
        self._categoria('Blusas', estoque=50)

        html = self._html()

        self.assertIn('width:0%', html.replace(' ', ''))


class PainelDasSalinhasTests(TestCase):

    def setUp(self):
        self.coord = Voluntario.objects.create_user(
            username='eventos', password='x', area='EVENTOS')
        self.bazar = Bazar.objects.create(
            nome='Edicao', data=timezone.localdate(),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=20,
            criado_por=self.coord)

    def _html(self):
        from bazar.views import painel

        pedido = RequestFactory().get('/bazar/painel/')
        pedido.user = self.coord
        pedido.session = SessionStore()
        resposta = painel(pedido)
        return (resposta.rendered_content if hasattr(resposta, 'rendered_content')
                else resposta.content.decode())

    def test_a_ordem_continua_sendo_a_OFICIAL_das_salinhas(self):
        """Ordenar por quantidade poria o Amarelo antes do Anil, e nao e assim
        que o projeto fala das salas (ver LISTA_SALAS)."""
        html = self._html()

        posicoes = [html.index(nome) for nome in
                    ('Violeta', 'Anil', 'Azul', 'Verde', 'Amarelo',
                     'Laranja', 'Vermelho', 'Família Feliz')]

        self.assertEqual(posicoes, sorted(posicoes))

    def test_salinha_sem_atendimento_continua_na_lista(self):
        """A sala que ainda nao veio e justamente a informacao acionavel
        durante o evento."""
        self.assertIn('Violeta', self._html())
