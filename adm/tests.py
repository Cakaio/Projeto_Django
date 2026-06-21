from django.test import TestCase, RequestFactory, Client
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from unittest.mock import MagicMock, patch
from adm.models import Categoria, Lancamento
from adm.views import AdmAcessoMixin, AdmEscritaMixin

User = get_user_model()


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


class CategoriaViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_adm = User.objects.create_user(
            username='adm_user', password='pass', area='ADM/FIN',
            first_name='ADM', last_name='User'
        )
        self.user_outro = User.objects.create_user(
            username='outro', password='pass', area='AZUL',
            first_name='Outro', last_name='User'
        )

    def test_lista_requer_login(self):
        resp = self.client.get('/adm/categorias/')
        self.assertEqual(resp.status_code, 302)

    def test_outro_bloqueado(self):
        self.client.login(username='outro', password='pass')
        resp = self.client.get('/adm/categorias/')
        self.assertEqual(resp.status_code, 403)

    def test_criar_categoria(self):
        self.client.login(username='adm_user', password='pass')
        resp = self.client.post('/adm/categorias/nova/', {
            'nome': 'Doação', 'tipo': 'RECEITA', 'ativo': True
        }, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Categoria.objects.filter(nome='Doação').exists())


class LancamentoViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_adm = User.objects.create_user(
            username='adm2', password='pass', area='ADM/FIN',
            first_name='ADM', last_name='Dois'
        )
        self.cat = Categoria.objects.create(nome='Doação', tipo='RECEITA')

    def test_criar_lancamento_manual(self):
        self.client.login(username='adm2', password='pass')
        resp = self.client.post('/adm/lancamentos/novo/', {
            'categoria': self.cat.pk,
            'valor': '500.00',
            'data': timezone.now().date().isoformat(),
            'descricao': 'Doação teste',
        }, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Lancamento.objects.filter(descricao='Doação teste').exists())

    def test_nao_edita_lancamento_supply(self):
        lan = Lancamento.objects.create(
            categoria=self.cat, valor='100', data=timezone.now().date(), origem='SUPPLY'
        )
        self.client.login(username='adm2', password='pass')
        resp = self.client.get(f'/adm/lancamentos/{lan.pk}/editar/', follow=False)
        self.assertEqual(resp.status_code, 302)
