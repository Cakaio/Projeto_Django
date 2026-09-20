"""A folha "Em qual caixa você está?" nao pode prender o voluntario.

Em 09/2026 ela abriu VAZIA no primeiro acesso do aparelho: o Bazar estava
aberto e nenhuma `SalaDoBazar` cadastrada. A folha cobria a tela, nao tinha
nenhum botao dentro e nao tinha como fechar. Para quem estava na fila, o Bazar
inteiro "nao carregava" — e a busca de atendido, que estava logo atras, parecia
quebrada.

O detalhe que fez o defeito passar: o `{% for sala in salas %}` estava certo
(lista vazia, nenhum botao), e o `{% if salas %}` faltava no ELEMENTO. Template
com laco vazio nao da erro; da uma caixa vazia.
"""
import datetime

from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase
from django.utils import timezone

from bazar.models import Bazar, SalaDoBazar

Voluntario = get_user_model()


class FolhaDoCaixaTests(TestCase):

    def setUp(self):
        self.pessoa = Voluntario(username='caixa1', area='EVENTOS')
        self.pessoa.set_password('x')
        self.pessoa.save()
        self.bazar = Bazar.objects.create(
            nome='Edicao de teste', data=timezone.localdate(),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=20,
            criado_por=self.pessoa)

    def _html(self):
        from bazar.views import atendimento

        pedido = RequestFactory().get('/bazar/')
        pedido.user = self.pessoa
        pedido.session = SessionStore()
        resposta = atendimento(pedido)
        return (resposta.rendered_content if hasattr(resposta, 'rendered_content')
                else resposta.content.decode())

    def test_sem_caixa_cadastrada_a_folha_nao_existe(self):
        """Pergunta sem resposta possivel nao e feita.

        O JavaScript abre a folha no primeiro acesso do aparelho. Se ela
        estiver no HTML sem nenhum botao dentro, o voluntario fica preso.
        """
        html = self._html()

        self.assertNotIn('data-caixa ', html)
        # E a tela continua usavel: a busca esta la.
        self.assertIn('data-busca', html)

    def test_com_caixa_cadastrada_a_folha_aparece_com_as_opcoes(self):
        SalaDoBazar.objects.create(bazar=self.bazar, nome='Mesa da entrada',
                                   ordem=1, ativo=True)
        SalaDoBazar.objects.create(bazar=self.bazar, nome='Mesa do fundo',
                                   ordem=2, ativo=True)

        html = self._html()

        self.assertIn('data-caixa ', html)
        self.assertIn('Mesa da entrada', html)
        self.assertIn('Mesa do fundo', html)

    def test_a_folha_sempre_tem_saida(self):
        """`sala` e OPCIONAL ao finalizar (bazar/views.py). Barrar a fila por
        um campo que o servidor nem exige troca uma coluna do relatorio pela
        manha inteira de atendimento."""
        SalaDoBazar.objects.create(bazar=self.bazar, nome='Mesa unica',
                                   ordem=1, ativo=True)

        html = self._html()

        self.assertIn('data-caixa-depois', html)
        self.assertIn('Decidir depois', html)

    def test_caixa_inativa_nao_vira_opcao(self):
        SalaDoBazar.objects.create(bazar=self.bazar, nome='Mesa desativada',
                                   ordem=1, ativo=False)

        html = self._html()

        self.assertNotIn('Mesa desativada', html)
        self.assertNotIn('data-caixa ', html)
