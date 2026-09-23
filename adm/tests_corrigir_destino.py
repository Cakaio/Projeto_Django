"""Corrigir a area/evento de um reembolso JA APROVADO ou JA PAGO.

Errar o destino na aprovacao e facil: os dois selects ficam ao lado dos botoes
de aprovar e rejeitar, num clique so. Ate agora nao havia como desfazer — o
teto da area errada ficava encolhido PARA SEMPRE, e o numero so parecia um
pouco maior do que devia, que e como esse tipo de erro sobrevive.

O que estes testes protegem: quem mexe no teto e o `Lancamento`, NAO o pedido.
Corrigir so o pedido deixaria a tela certa e o teto errado.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from adm import views
from adm.models import Categoria, Evento, TetoArea
from adm.servicos import situacao_dos_tetos
from forms_pcf.models import PedidoReembolso
from forms_pcf.views import sincronizar_lancamento_do_reembolso

Voluntario = get_user_model()
HOJE = datetime.date(2026, 9, 19)


def pedido_http(usuario, dados=None):
    req = RequestFactory().post('/x/', dados or {})
    req.user = usuario
    req.session = SessionStore()
    req._messages = FallbackStorage(req)
    return req


class CorrigirDestinoTests(TestCase):

    def setUp(self):
        self.adm = Voluntario.objects.create_user(
            username='adm', password='x', area='ADM/FIN')
        self.ana = Voluntario.objects.create_user(
            username='ana', password='x', area='AMARELO')
        self.categoria = Categoria.objects.create(nome='Gasolina',
                                                  tipo='DESPESA')
        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.ana, valor=Decimal('50.00'), descricao='gasolina',
            data_gasto=HOJE, categoria=self.categoria, status='APROVADO',
            area='AMARELO')
        # Como a aprovacao faz: o lancamento nasce ali.
        sincronizar_lancamento_do_reembolso(self.pedido, self.adm)
        self.pedido.save()

    def _corrigir(self, **dados):
        resposta = views.reembolso_corrigir_destino(
            pedido_http(self.adm, dados), pk=self.pedido.pk)
        self.pedido.refresh_from_db()
        return resposta

    def _gasto_de(self, area):
        linha = next((l for l in situacao_dos_tetos(HOJE)
                      if l['area'] == area), None)
        return linha['gasto'] if linha else Decimal('0')

    # ── o que a correcao precisa mesmo fazer ─────────────────────────────
    def test_o_LANCAMENTO_acompanha_a_correcao(self):
        """Quem mexe no teto e o lancamento. Corrigir so o pedido deixaria a
        tela certa e o teto errado."""
        self._corrigir(area='ANIL')

        self.assertEqual(self.pedido.area, 'ANIL')
        self.assertEqual(self.pedido.lancamento.area, 'ANIL')

    def test_o_TETO_das_duas_areas_muda(self):
        TetoArea.objects.create(area='AMARELO', valor=Decimal('500.00'))
        TetoArea.objects.create(area='ANIL', valor=Decimal('500.00'))
        self.assertEqual(self._gasto_de('AMARELO'), Decimal('50.00'))

        self._corrigir(area='ANIL')

        self.assertEqual(self._gasto_de('AMARELO'), Decimal('0'))
        self.assertEqual(self._gasto_de('ANIL'), Decimal('50.00'))

    def test_de_area_para_NENHUMA(self):
        """O caso que motivou o pedido: aprovou com area sem querer."""
        TetoArea.objects.create(area='AMARELO', valor=Decimal('500.00'))

        self._corrigir(area='')

        self.assertEqual(self.pedido.area, '')
        self.assertEqual(self.pedido.lancamento.area, '')
        self.assertEqual(self._gasto_de('AMARELO'), Decimal('0'))

    def test_trocar_area_por_evento(self):
        """Evento deixa a area VAZIA: gasolina da Festa Junina nao e gasto do
        Amarelo nem da equipe de EVENTOS."""
        evento = Evento.objects.create(nome='Festa Junina')

        self._corrigir(area='', evento=str(evento.pk))

        self.assertEqual(self.pedido.evento_id, evento.pk)
        self.assertEqual(self.pedido.area, '')
        self.assertEqual(self.pedido.lancamento.evento_id, evento.pk)

    def test_corrigir_reembolso_JA_PAGO_funciona(self):
        """Move o gasto de um teto para outro RETROATIVAMENTE — e o que foi
        pedido, e a tela avisa disso na confirmacao."""
        self.pedido.status = 'PAGO'
        self.pedido.save()

        self._corrigir(area='ANIL')

        self.assertEqual(self.pedido.area, 'ANIL')
        self.assertEqual(self.pedido.lancamento.area, 'ANIL')

    # ── fica registrado quem mexeu ───────────────────────────────────────
    def test_grava_quem_corrigiu_e_quando(self):
        """Mudar qual area consumiu o teto e correcao financeira: quando dois
        lideres olharem o mesmo numero e discordarem, precisa dar para saber
        quem mexeu."""
        self._corrigir(area='ANIL')

        self.assertEqual(self.pedido.destino_corrigido_por, self.adm)
        self.assertIsNotNone(self.pedido.destino_corrigido_em)

    # ── o que e recusado ─────────────────────────────────────────────────
    def test_pendente_nao_tem_destino_para_corrigir(self):
        """PENDENTE ainda nao tem lancamento — ele nasce na aprovacao. Mexer
        ali daria a impressao de ter mexido no teto, sem ter mexido."""
        self.pedido.status = 'PENDENTE'
        self.pedido.save()

        self._corrigir(area='ANIL')

        self.assertEqual(self.pedido.area, 'AMARELO')

    def test_rejeitado_nao_tem_destino_para_corrigir(self):
        self.pedido.status = 'REJEITADO'
        self.pedido.save()

        self._corrigir(area='ANIL')

        self.assertEqual(self.pedido.area, 'AMARELO')

    def test_area_inexistente_e_recusada(self):
        self._corrigir(area='SALA_QUE_NAO_EXISTE')

        self.assertEqual(self.pedido.area, 'AMARELO')

    def test_quem_nao_e_ADM_FIN_nao_corrige(self):
        for area in ('AMARELO', 'SUPPLY', 'TRIADE'):
            de_fora = Voluntario.objects.create_user(
                username=f'u{area}', password='x', area=area)
            with self.assertRaises(PermissionDenied, msg=area):
                views.reembolso_corrigir_destino(
                    pedido_http(de_fora, {'area': 'ANIL'}), pk=self.pedido.pk)

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.area, 'AMARELO')

    def test_GET_nao_corrige(self):
        """Corrigir move dinheiro entre tetos: um link colado no grupo nao
        pode fazer isso em nome de quem clicar."""
        from django.http import HttpResponseNotAllowed

        req = RequestFactory().get('/x/')
        req.user = self.adm
        req.session = SessionStore()
        req._messages = FallbackStorage(req)

        resposta = views.reembolso_corrigir_destino(req, pk=self.pedido.pk)

        self.pedido.refresh_from_db()
        self.assertIsInstance(resposta, HttpResponseNotAllowed)
        self.assertEqual(self.pedido.area, 'AMARELO')


class BotaoNaListaTests(TestCase):

    def setUp(self):
        self.adm = Voluntario.objects.create_user(
            username='adm', password='x', area='ADM/FIN')
        self.ana = Voluntario.objects.create_user(
            username='ana', password='x', area='AMARELO')
        categoria = Categoria.objects.create(nome='Gasolina', tipo='DESPESA')
        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.ana, valor=Decimal('50.00'), descricao='gasolina',
            data_gasto=HOJE, categoria=categoria, status='APROVADO',
            area='AMARELO')

    def _html(self, usuario=None, status='APROVADO'):
        req = RequestFactory().get('/adm/reembolsos/', {'status': status})
        req.user = usuario or self.adm
        req.session = SessionStore()
        req._messages = FallbackStorage(req)
        resposta = views.reembolsos(req)
        return (resposta.rendered_content if hasattr(resposta, 'rendered_content')
                else resposta.content.decode())

    def test_o_aprovado_ganha_o_botao_de_corrigir(self):
        self.assertIn('Corrigir destino', self._html())

    def test_o_pago_tambem_ganha(self):
        self.pedido.status = 'PAGO'
        self.pedido.save()

        self.assertIn('Corrigir destino', self._html(status='PAGO'))

    def test_a_confirmacao_avisa_que_o_teto_muda_agora(self):
        """Corrigir um pedido JA PAGO move o gasto retroativamente: se o
        semestre ja foi fechado na cabeca de alguem, o numero dele muda depois
        do fato. A tela precisa dizer isso antes."""
        self.assertIn('mesmo que o pedido já esteja pago', self._html())

    def test_quem_nao_e_ADM_FIN_nao_ve_o_botao(self):
        triade = Voluntario.objects.create_user(
            username='tri', password='x', area='TRIADE')

        self.assertNotIn('Corrigir destino', self._html(usuario=triade))
