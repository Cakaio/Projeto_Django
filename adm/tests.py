from django.test import TestCase, RequestFactory
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from unittest.mock import MagicMock, patch
from adm.models import Categoria, Lancamento
from adm.views import AdmAcessoMixin, AdmEscritaMixin


class CategoriaModelTest(TestCase):
    def test_str(self):
        cat = Categoria(nome='Doação', tipo='RECEITA')
        self.assertEqual(str(cat), 'Doação (Receita)')


class LancamentoModelTest(TestCase):
    def setUp(self):
        self.cat_receita = Categoria.objects.create(nome='Doação', tipo='RECEITA')
        self.cat_despesa = Categoria.objects.create(nome='Materiais', tipo='DESPESA')

    def test_tipo_derivado_da_categoria(self):
        """tipo deve ser preenchido automaticamente a partir da categoria"""
        lan = Lancamento.objects.create(
            categoria=self.cat_receita,
            valor='100.00',
            data=timezone.now().date(),
        )
        self.assertEqual(lan.tipo, 'RECEITA')

    def test_tipo_despesa_derivado(self):
        lan = Lancamento.objects.create(
            categoria=self.cat_despesa,
            valor='50.00',
            data=timezone.now().date(),
        )
        self.assertEqual(lan.tipo, 'DESPESA')


class MixinTest(TestCase):
    def _make_user(self, area, superuser=False):
        u = MagicMock()
        u.is_authenticated = True
        u.is_superuser = superuser
        u.area = area
        return u

    def _make_request(self, area, superuser=False):
        req = MagicMock()
        req.user = self._make_user(area, superuser)
        return req

    def test_adm_fin_tem_acesso_leitura(self):
        """ADM/FIN deve passar pela verificação de acesso sem PermissionDenied."""
        mixin = AdmAcessoMixin()
        mixin.handle_no_permission = MagicMock()
        req = self._make_request('ADM/FIN')
        raised = False
        try:
            with patch('adm.views.super') as mock_super:
                mock_super.return_value.dispatch = MagicMock(return_value=None)
                mixin.dispatch(req)
        except PermissionDenied:
            raised = True
        self.assertFalse(raised, "ADM/FIN não deve receber PermissionDenied")

    def test_voluntario_sem_area_bloqueado(self):
        """Voluntário de área não autorizada deve receber PermissionDenied."""
        mixin = AdmAcessoMixin()
        mixin.handle_no_permission = MagicMock()
        req = self._make_request('AZUL')
        with self.assertRaises(PermissionDenied):
            mixin.dispatch(req)
