"""As telas do rateio: quem mexe, o que e recusado, e o selo de fechado.

`RequestFactory` e nao `self.client` de proposito: o test Client do Django
quebra ao renderizar template neste ambiente ('super' object has no attribute
'dicts'). Chamar a view direto exercita os templates DE VERDADE e nao depende
do Client.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from adm import views
from adm.models import LinhaDeRateio, RateioDeGasto

Voluntario = get_user_model()
SABADO = datetime.date(2026, 9, 19)


def pedido(metodo, caminho, usuario, dados=None):
    """Um request completo, como o middleware entregaria."""
    fabrica = RequestFactory()
    req = (fabrica.post(caminho, dados or {}) if metodo == 'post'
           else fabrica.get(caminho, dados or {}))
    req.user = usuario
    req.session = SessionStore()
    req._messages = FallbackStorage(req)
    return req


def corpo(resposta):
    return (resposta.rendered_content if hasattr(resposta, 'rendered_content')
            else resposta.content.decode())


class PermissaoTests(TestCase):
    """Rateia quem tem a nota na mao: ADM/FIN. Nao e o Supply."""

    def setUp(self):
        self.rateio = RateioDeGasto.objects.create(
            data=SABADO, total_a_ratear=Decimal('800.00'))

    def _pessoa(self, area):
        return Voluntario.objects.create_user(
            username=f'u{area}'.replace('/', ''), password='x', area=area)

    def test_adm_fin_rateia(self):
        req = pedido('get', f'/adm/rateios/{self.rateio.pk}/', self._pessoa('ADM/FIN'))

        resposta = views.rateio_detalhe(req, pk=self.rateio.pk)

        self.assertEqual(resposta.status_code, 200)

    def test_supply_nao_rateia(self):
        """O Supply avisa "conferi os numeros do sabado"; quem lanca o valor e
        a ADM. Deixar o Supply ratear faria ele responder por um numero que
        nao lanca."""
        req = pedido('get', f'/adm/rateios/{self.rateio.pk}/', self._pessoa('SUPPLY'))

        with self.assertRaises(PermissionDenied):
            views.rateio_detalhe(req, pk=self.rateio.pk)

    def test_triade_le_a_lista_mas_nao_rateia(self):
        triade = self._pessoa('TRIADE')

        lista = views.rateios(pedido('get', '/adm/rateios/', triade))
        self.assertEqual(lista.status_code, 200)

        with self.assertRaises(PermissionDenied):
            views.rateio_detalhe(
                pedido('get', f'/adm/rateios/{self.rateio.pk}/', triade),
                pk=self.rateio.pk)


class RatearTests(TestCase):

    def setUp(self):
        self.adm = Voluntario.objects.create_user(
            username='adm', password='x', area='ADM/FIN')
        self.rateio = RateioDeGasto.objects.create(
            data=SABADO, total_a_ratear=Decimal('800.00'))
        self.url = f'/adm/rateios/{self.rateio.pk}/'

    def _acrescentar(self, area, valor):
        req = pedido('post', self.url, self.adm, {'area': area, 'valor': valor})
        return views.rateio_detalhe(req, pk=self.rateio.pk)

    def test_acrescentar_uma_salinha(self):
        self._acrescentar('FAMILIA_FELIZ', '34.00')

        linha = self.rateio.linhas.get()
        self.assertEqual(linha.area, 'FAMILIA_FELIZ')
        self.assertEqual(linha.valor, Decimal('34.00'))

    def test_ratear_acima_do_total_e_recusado(self):
        """Isso e dedo errado, nao trabalho pela metade."""
        self._acrescentar('AMARELO', '900.00')

        self.assertEqual(self.rateio.linhas.count(), 0)

    def test_a_recusa_diz_quanto_ainda_cabe(self):
        self._acrescentar('AMARELO', '700.00')

        resposta = self._acrescentar('ANIL', '200.00')

        self.assertIn('Só faltam R$ 100', corpo(resposta))

    def test_valor_zero_ou_negativo_e_recusado(self):
        self._acrescentar('AMARELO', '0')
        self._acrescentar('ANIL', '-5')

        self.assertEqual(self.rateio.linhas.count(), 0)

    def test_area_repetida_e_recusada_com_instrucao(self):
        self._acrescentar('AMARELO', '10.00')

        resposta = self._acrescentar('AMARELO', '20.00')

        self.assertEqual(self.rateio.linhas.count(), 1)
        self.assertIn('Some no valor da linha existente', corpo(resposta))

    def test_tirar_uma_linha(self):
        self._acrescentar('AMARELO', '10.00')
        linha = self.rateio.linhas.get()

        views.rateio_linha_deletar(
            pedido('post', f'{self.url}linha/{linha.pk}/deletar/', self.adm),
            pk=self.rateio.pk, linha_pk=linha.pk)

        self.assertEqual(self.rateio.linhas.count(), 0)


class FecharTests(TestCase):

    def setUp(self):
        self.adm = Voluntario.objects.create_user(
            username='adm', password='x', area='ADM/FIN')
        self.rateio = RateioDeGasto.objects.create(
            data=SABADO, total_a_ratear=Decimal('100.00'))
        self.url = f'/adm/rateios/{self.rateio.pk}/'

    def _fechar(self):
        return views.rateio_fechar(
            pedido('post', f'{self.url}fechar/', self.adm), pk=self.rateio.pk)

    def test_nao_fecha_com_sobra(self):
        """Fechar com sobra transformaria 'esqueci metade' em 'conferido'."""
        LinhaDeRateio.objects.create(rateio=self.rateio, area='AMARELO',
                                     valor=Decimal('60.00'))

        self._fechar()

        self.rateio.refresh_from_db()
        self.assertTrue(self.rateio.esta_aberto)

    def test_fecha_quando_bate(self):
        LinhaDeRateio.objects.create(rateio=self.rateio, area='AMARELO',
                                     valor=Decimal('100.00'))

        self._fechar()

        self.rateio.refresh_from_db()
        self.assertFalse(self.rateio.esta_aberto)
        self.assertEqual(self.rateio.fechado_por, self.adm)

    def test_tirar_linha_de_rateio_fechado_REABRE(self):
        """Deixar o selo de 'conferido' num numero que mudou e pior que nao
        ter selo nenhum."""
        linha = LinhaDeRateio.objects.create(
            rateio=self.rateio, area='AMARELO', valor=Decimal('100.00'))
        self._fechar()

        views.rateio_linha_deletar(
            pedido('post', f'{self.url}linha/{linha.pk}/deletar/', self.adm),
            pk=self.rateio.pk, linha_pk=linha.pk)

        self.rateio.refresh_from_db()
        self.assertTrue(self.rateio.esta_aberto)

    def test_fechar_de_novo_reabre(self):
        LinhaDeRateio.objects.create(rateio=self.rateio, area='AMARELO',
                                     valor=Decimal('100.00'))
        self._fechar()

        self._fechar()

        self.rateio.refresh_from_db()
        self.assertTrue(self.rateio.esta_aberto)

    def test_get_nao_fecha(self):
        """Fechar grava o nome de uma pessoa como responsavel pelo numero: um
        link colado no grupo nao pode fechar em nome de quem clicar."""
        from django.http import HttpResponseNotAllowed

        LinhaDeRateio.objects.create(rateio=self.rateio, area='AMARELO',
                                     valor=Decimal('100.00'))

        resposta = views.rateio_fechar(
            pedido('get', f'{self.url}fechar/', self.adm), pk=self.rateio.pk)

        self.rateio.refresh_from_db()
        self.assertTrue(self.rateio.esta_aberto)
        self.assertIsInstance(resposta, HttpResponseNotAllowed)


class ListaTests(TestCase):

    def test_a_lista_denuncia_quanto_falta_nos_abertos(self):
        """Rateio aberto precisa INCOMODAR: esquecido, ele deixa o teto da
        salinha menor que a realidade em silencio."""
        adm = Voluntario.objects.create_user(
            username='adm', password='x', area='ADM/FIN')
        aberto = RateioDeGasto.objects.create(
            data=SABADO, total_a_ratear=Decimal('800.00'))
        LinhaDeRateio.objects.create(rateio=aberto, area='AMARELO',
                                     valor=Decimal('154.00'))

        html = corpo(views.rateios(pedido('get', '/adm/rateios/', adm)))

        self.assertIn('646', html)
        self.assertIn('em aberto', html)
