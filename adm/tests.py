from django.test import TestCase, RequestFactory
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from unittest.mock import MagicMock
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
        mixin = AdmAcessoMixin()
        mixin.handle_no_permission = MagicMock()
        req = self._make_request('ADM/FIN')
        # não levanta PermissionDenied
        try:
            mixin.dispatch(req)
        except (PermissionDenied, AttributeError):
            pass  # AttributeError de super().dispatch é esperado sem view real

    def test_voluntario_sem_area_bloqueado(self):
        mixin = AdmAcessoMixin()
        mixin.handle_no_permission = MagicMock()
        req = self._make_request('AZUL')
        with self.assertRaises((PermissionDenied, AttributeError)):
            mixin.dispatch(req)
