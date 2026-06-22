import io
from django.test import TestCase, Client
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
from forms_pcf.models import FeedbackArea, PedidoReembolso, ReceptorNotificacaoReembolso
from adm.models import Categoria, Lancamento

User = get_user_model()


class FeedbackAreaModelTest(TestCase):
    def test_criado_sem_usuario(self):
        fb = FeedbackArea.objects.create(area='PROJETOS', descricao='Dor de teste')
        self.assertIsNone(getattr(fb, 'criado_por', None))
        self.assertIsNotNone(fb.criado_em)

    def test_str(self):
        fb = FeedbackArea(area='PROJETOS', descricao='Dor')
        self.assertIn('PROJETOS', str(fb))


class PedidoReembolsoModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='vol', password='pw', area='MARKETING',
            first_name='Ana', last_name='Silva'
        )
        self.cat = Categoria.objects.create(nome='Transporte', tipo='DESPESA')

    def test_status_default_pendente(self):
        p = PedidoReembolso.objects.create(
            solicitante=self.user,
            valor=Decimal('50.00'),
            descricao='Uber',
            data_gasto=timezone.now().date(),
            categoria=self.cat,
            comprovante='reembolsos/fake.jpg',
        )
        self.assertEqual(p.status, 'PENDENTE')

    def test_str(self):
        p = PedidoReembolso(valor=Decimal('100.00'), status='PENDENTE')
        self.assertIn('100', str(p))


class ReceptorNotificacaoTest(TestCase):
    def test_str(self):
        r = ReceptorNotificacaoReembolso(nome='Maria', email='m@pcf.org')
        self.assertIn('Maria', str(r))

    def test_ativo_default(self):
        r = ReceptorNotificacaoReembolso.objects.create(nome='João', email='j@pcf.org')
        self.assertTrue(r.ativo)


class AdmOrigemReembolsoTest(TestCase):
    def test_origem_choices_contem_reembolso(self):
        from adm.models import ORIGEM_CHOICES
        valores = [v for v, _ in ORIGEM_CHOICES]
        self.assertIn('REEMBOLSO', valores)


class EnviarFeedbackViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='vol2', password='pw', area='MARKETING')
        self.client.force_login(self.user)

    def test_get_retorna_200(self):
        resp = self.client.get(reverse('forms_pcf:feedback'))
        self.assertEqual(resp.status_code, 200)

    def test_post_valido_cria_feedback_e_redireciona(self):
        resp = self.client.post(reverse('forms_pcf:feedback'), {
            'area': 'MARKETING',
            'descricao': 'Precisamos de mais comunicação entre áreas.',
        })
        self.assertRedirects(resp, reverse('forms_pcf:feedback_sucesso'))
        self.assertEqual(FeedbackArea.objects.count(), 1)
        fb = FeedbackArea.objects.first()
        self.assertEqual(fb.area, 'MARKETING')

    def test_post_invalido_nao_cria(self):
        resp = self.client.post(reverse('forms_pcf:feedback'), {'area': '', 'descricao': ''})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(FeedbackArea.objects.count(), 0)

    def test_anonimo_redireciona_login(self):
        self.client.logout()
        resp = self.client.get(reverse('forms_pcf:feedback'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)


class FeedbackInboxPermissionTest(TestCase):
    def _login(self, area, superuser=False):
        c = Client()
        u = User.objects.create_user(
            username=f'u_{area}', password='pw', area=area, is_superuser=superuser
        )
        c.force_login(u)
        return c

    def test_projetos_tem_acesso(self):
        resp = self._login('PROJETOS').get(reverse('forms_pcf:feedback_inbox'))
        self.assertEqual(resp.status_code, 200)

    def test_triade_tem_acesso(self):
        resp = self._login('TRIADE').get(reverse('forms_pcf:feedback_inbox'))
        self.assertEqual(resp.status_code, 200)

    def test_superuser_tem_acesso(self):
        resp = self._login('MARKETING', superuser=True).get(reverse('forms_pcf:feedback_inbox'))
        self.assertEqual(resp.status_code, 200)

    def test_outros_recebem_403(self):
        resp = self._login('MARKETING').get(reverse('forms_pcf:feedback_inbox'))
        self.assertEqual(resp.status_code, 403)
