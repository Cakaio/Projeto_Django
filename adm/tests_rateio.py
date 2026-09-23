"""Rateio de gasto: descontar o teto SEM descontar o caixa.

O defeito que este modelo existe para impedir: lancar o gasto da salinha como
despesa, ALEM do lancamento do cartao, e contar o mesmo dinheiro duas vezes.
Os R$800 dos cartoes mais os R$800 rateados virariam R$1.600 de gasto que nao
existiu — e ninguem percebe, porque o numero so fica "um pouco maior".
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from adm.models import (Categoria, Conta, Lancamento, LinhaDeRateio,
                        RateioDeGasto, TetoArea)
from adm.servicos import saldo_das_contas, situacao_dos_tetos

Voluntario = get_user_model()
SABADO = datetime.date(2026, 9, 19)


class RateioNaoTocaNoCaixaTests(TestCase):
    """A razao de ser do modelo separado."""

    def setUp(self):
        self.adm = Voluntario.objects.create_user(
            username='adm', password='x', area='ADM/FIN')
        self.categoria = Categoria.objects.create(
            nome='Materiais de Supply', tipo='DESPESA')
        self.cartao = Conta.objects.create(
            nome='Cartao da Ana', tipo='CARTAO', controla_saldo=True)

    def _lancamento_do_cartao(self, valor):
        """Como a ADM lanca: categoria, conta, e AREA VAZIA."""
        return Lancamento.objects.create(
            tipo='DESPESA', categoria=self.categoria, valor=Decimal(valor),
            data=SABADO, conta=self.cartao, area='')

    def _rateio(self, total, **linhas):
        rateio = RateioDeGasto.objects.create(
            data=SABADO, total_a_ratear=Decimal(total), criado_por=self.adm)
        for area, valor in linhas.items():
            LinhaDeRateio.objects.create(rateio=rateio, area=area,
                                         valor=Decimal(valor))
        return rateio

    def test_o_rateio_nao_entra_no_total_de_despesas(self):
        """O caixa continua sabendo que saiu R$800, nao R$1.600."""
        self._lancamento_do_cartao('800.00')
        self._rateio('800.00', FAMILIA_FELIZ='34.00', AMARELO='766.00')

        total = sum(l.valor for l in Lancamento.objects.filter(tipo='DESPESA'))

        self.assertEqual(total, Decimal('800.00'))

    def test_o_rateio_nao_desconta_saldo_de_cartao_nenhum(self):
        """Rateio nao e `Lancamento`: nao ha como ele entrar aqui."""
        self._lancamento_do_cartao('800.00')
        self._rateio('800.00', FAMILIA_FELIZ='800.00')

        linha = [l for l in saldo_das_contas()
                 if l['conta'].pk == self.cartao.pk][0]

        self.assertEqual(linha['gasto'], Decimal('800.00'))

    def test_o_rateio_DESCONTA_o_teto_da_area(self):
        TetoArea.objects.create(area='FAMILIA_FELIZ', valor=Decimal('500.00'))
        self._lancamento_do_cartao('800.00')
        self._rateio('800.00', FAMILIA_FELIZ='34.00')

        ff = self._linha_do_ff()

        self.assertEqual(ff['gasto'], Decimal('34.00'))
        self.assertEqual(ff['disponivel'], Decimal('466.00'))

    def _linha_do_ff(self):
        return [l for l in situacao_dos_tetos(SABADO)
                if l['area'] == 'FAMILIA_FELIZ'][0]

    def test_lancamento_com_area_e_rateio_SOMAM_no_teto(self):
        """O reembolso continua descontando o teto, e o rateio se soma a ele.

        Sao coisas diferentes e as duas pesam: no reembolso o dinheiro sai
        agora; no rateio ele ja saiu antes, pelo cartao.
        """
        TetoArea.objects.create(area='FAMILIA_FELIZ', valor=Decimal('500.00'))
        Lancamento.objects.create(
            tipo='DESPESA', categoria=self.categoria, valor=Decimal('200.00'),
            data=SABADO, area='FAMILIA_FELIZ')          # reembolso
        self._rateio('800.00', FAMILIA_FELIZ='34.00')   # rateio do Supply

        self.assertEqual(self._linha_do_ff()['gasto'], Decimal('234.00'))

    def test_a_linha_do_teto_separa_as_duas_origens(self):
        """Sem isto o lider da salinha ve o teto encolher e procura um
        lancamento que NAO EXISTE."""
        TetoArea.objects.create(area='FAMILIA_FELIZ', valor=Decimal('500.00'))
        Lancamento.objects.create(
            tipo='DESPESA', categoria=self.categoria, valor=Decimal('200.00'),
            data=SABADO, area='FAMILIA_FELIZ')
        self._rateio('800.00', FAMILIA_FELIZ='34.00')

        ff = self._linha_do_ff()

        self.assertEqual(ff['gasto_lancado'], Decimal('200.00'))
        self.assertEqual(ff['gasto_rateado'], Decimal('34.00'))

    def test_area_que_so_aparece_no_rateio_entra_na_tela(self):
        """Gastou sem teto definido continua sendo o que a tela denuncia."""
        self._rateio('100.00', ANIL='100.00')

        areas = {l['area'] for l in situacao_dos_tetos(SABADO)}

        self.assertIn('ANIL', areas)

    def test_rateio_de_outro_semestre_nao_conta(self):
        TetoArea.objects.create(area='FAMILIA_FELIZ', valor=Decimal('500.00'))
        antigo = RateioDeGasto.objects.create(
            data=datetime.date(2026, 3, 14), total_a_ratear=Decimal('100.00'))
        LinhaDeRateio.objects.create(rateio=antigo, area='FAMILIA_FELIZ',
                                     valor=Decimal('100.00'))

        self.assertEqual(self._linha_do_ff()['gasto'], Decimal('0'))


class RegrasDoRateioTests(TestCase):

    def setUp(self):
        self.rateio = RateioDeGasto.objects.create(
            data=SABADO, total_a_ratear=Decimal('800.00'))

    def test_rateio_novo_nasce_aberto(self):
        self.assertTrue(self.rateio.esta_aberto)
        self.assertEqual(self.rateio.falta_ratear, Decimal('800.00'))

    def test_rateado_e_falta_acompanham_as_linhas(self):
        LinhaDeRateio.objects.create(rateio=self.rateio, area='AMARELO',
                                     valor=Decimal('120.00'))
        LinhaDeRateio.objects.create(rateio=self.rateio, area='ANIL',
                                     valor=Decimal('34.00'))

        self.assertEqual(self.rateio.rateado, Decimal('154.00'))
        self.assertEqual(self.rateio.falta_ratear, Decimal('646.00'))

    def test_so_pode_fechar_quando_bate_no_centavo(self):
        """Fechar com sobra transformaria 'esqueci metade' em 'conferido'."""
        LinhaDeRateio.objects.create(rateio=self.rateio, area='AMARELO',
                                     valor=Decimal('799.99'))
        self.assertFalse(self.rateio.pode_fechar)

        LinhaDeRateio.objects.create(rateio=self.rateio, area='ANIL',
                                     valor=Decimal('0.01'))
        self.assertTrue(self.rateio.pode_fechar)

    def test_uma_linha_por_area(self):
        """Duas linhas da mesma area deixariam a soma ambigua e a tela
        mostrando a salinha duas vezes."""
        LinhaDeRateio.objects.create(rateio=self.rateio, area='AMARELO',
                                     valor=Decimal('10.00'))

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                LinhaDeRateio.objects.create(rateio=self.rateio,
                                             area='AMARELO',
                                             valor=Decimal('20.00'))

    def test_a_mesma_area_em_rateios_diferentes_e_permitida(self):
        outro = RateioDeGasto.objects.create(
            data=datetime.date(2026, 9, 26), total_a_ratear=Decimal('50.00'))
        LinhaDeRateio.objects.create(rateio=self.rateio, area='AMARELO',
                                     valor=Decimal('10.00'))
        LinhaDeRateio.objects.create(rateio=outro, area='AMARELO',
                                     valor=Decimal('20.00'))

        self.assertEqual(LinhaDeRateio.objects.filter(area='AMARELO').count(), 2)

    def test_apagar_o_rateio_leva_as_linhas(self):
        LinhaDeRateio.objects.create(rateio=self.rateio, area='AMARELO',
                                     valor=Decimal('10.00'))

        self.rateio.delete()

        self.assertEqual(LinhaDeRateio.objects.count(), 0)
