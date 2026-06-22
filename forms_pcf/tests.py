from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
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
