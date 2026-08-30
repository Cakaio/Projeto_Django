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


from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile


class EnviarReembolsoViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='req', password='pw', area='MARKETING')
        self.client.force_login(self.user)
        self.cat = Categoria.objects.create(nome='Transporte', tipo='DESPESA')
        ReceptorNotificacaoReembolso.objects.create(nome='ADM1', email='adm@pcf.org', ativo=True)
        ReceptorNotificacaoReembolso.objects.create(nome='ADM2', email='adm2@pcf.org', ativo=False)

    @patch('forms_pcf.views.send_mail')
    def test_post_valido_cria_pedido_e_envia_email(self, mock_mail):
        arquivo = SimpleUploadedFile('comp.jpg', b'fake', content_type='image/jpeg')
        resp = self.client.post(reverse('forms_pcf:reembolso'), {
            'valor': '75.50',
            'descricao': 'Uber para evento',
            'data_gasto': timezone.now().date().isoformat(),
            'categoria': self.cat.pk,
            'comprovante': arquivo,
        })
        self.assertRedirects(resp, reverse('forms_pcf:reembolso_sucesso'))
        self.assertEqual(PedidoReembolso.objects.count(), 1)
        pedido = PedidoReembolso.objects.first()
        self.assertEqual(pedido.status, 'PENDENTE')
        self.assertEqual(pedido.solicitante, self.user)
        # Só o receptor ativo deve receber
        self.assertEqual(mock_mail.call_count, 1)
        call_kwargs = mock_mail.call_args
        self.assertIn('adm@pcf.org', call_kwargs[1].get('recipient_list', call_kwargs[0][3] if len(call_kwargs[0]) > 3 else []))

    @patch('forms_pcf.views.send_mail')
    def test_pedido_ja_nasce_com_a_area_de_quem_pediu(self, mock_mail):
        """O formulário não pergunta a área — ela sai do solicitante.

        Sem isso o pedido chegava na fila da ADM como "sem área nem evento", e
        só era atribuído no pagamento: até lá ninguém sabia de qual teto aquele
        dinheiro sairia.
        """
        arquivo = SimpleUploadedFile('comp.jpg', b'fake', content_type='image/jpeg')
        self.client.post(reverse('forms_pcf:reembolso'), {
            'valor': '30.00',
            'descricao': 'Gasolina',
            'data_gasto': timezone.now().date().isoformat(),
            'categoria': self.cat.pk,
            'comprovante': arquivo,
        })
        pedido = PedidoReembolso.objects.get()
        self.assertEqual(pedido.area, 'MARKETING')

    @patch('forms_pcf.views.send_mail')
    def test_a_area_preenchida_sobrevive_ao_pagamento(self, mock_mail):
        """O caso comum: gasto da própria área, ninguém precisa escolher nada.

        Antes a ADM tinha que escolher a área na mão em todo pagamento, porque
        o campo chegava vazio.
        """
        from adm.models import Conta
        from forms_pcf.forms import PagamentoReembolsoForm

        arquivo = SimpleUploadedFile('comp.jpg', b'fake', content_type='image/jpeg')
        self.client.post(reverse('forms_pcf:reembolso'), {
            'valor': '30.00',
            'descricao': 'Gasolina',
            'data_gasto': timezone.now().date().isoformat(),
            'categoria': self.cat.pk,
            'comprovante': arquivo,
        })
        pedido = PedidoReembolso.objects.get()

        conta = Conta.objects.create(nome='Banco do Brasil')
        form = PagamentoReembolsoForm(
            data={
                'conta_pagamento': conta.pk,
                'pago_em': timezone.now().date().isoformat(),
                # A área já vem preenchida no formulário; a ADM só confirma.
                'area': pedido.area,
                'evento': '',
            },
            files={'comprovante_pagamento': SimpleUploadedFile(
                'pago.jpg', b'fake', content_type='image/jpeg')},
            instance=pedido,
        )
        self.assertTrue(form.is_valid(), form.errors)
        pago = form.save()

        self.assertEqual(pago.area, 'MARKETING')
        self.assertIsNone(pago.evento)

    def test_sem_comprovante_nao_cria(self):
        resp = self.client.post(reverse('forms_pcf:reembolso'), {
            'valor': '10.00',
            'descricao': 'Sem comp',
            'data_gasto': timezone.now().date().isoformat(),
            'categoria': self.cat.pk,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PedidoReembolso.objects.count(), 0)


class AprovarReembolsoViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.adm = User.objects.create_user(username='adm', password='pw', area='ADM/FIN')
        self.client.force_login(self.adm)
        self.cat = Categoria.objects.create(nome='Material', tipo='DESPESA')
        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.adm,
            valor=Decimal('120.00'),
            descricao='Materiais',
            data_gasto=timezone.now().date(),
            categoria=self.cat,
            comprovante='reembolsos/fake.jpg',
            status='PENDENTE',
        )

    def test_aprovacao_cria_lancamento_e_atualiza_status(self):
        resp = self.client.post(reverse('forms_pcf:reembolso_aprovar', args=[self.pedido.pk]))
        self.assertRedirects(resp, reverse('forms_pcf:reembolso_inbox'))
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'APROVADO')
        self.assertIsNotNone(self.pedido.lancamento)
        lan = self.pedido.lancamento
        self.assertEqual(lan.origem, 'REEMBOLSO')
        self.assertEqual(lan.valor, Decimal('120.00'))
        self.assertEqual(lan.tipo, 'DESPESA')

    def test_nao_adm_recebe_403(self):
        outro = User.objects.create_user(username='out', password='pw', area='MARKETING')
        c = Client()
        c.force_login(outro)
        resp = c.post(reverse('forms_pcf:reembolso_aprovar', args=[self.pedido.pk]))
        self.assertEqual(resp.status_code, 403)


class RejeitarReembolsoViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.adm = User.objects.create_user(username='adm2', password='pw', area='ADM/FIN')
        self.client.force_login(self.adm)
        self.cat = Categoria.objects.create(nome='Outro', tipo='DESPESA')
        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.adm,
            valor=Decimal('30.00'),
            descricao='Gasto',
            data_gasto=timezone.now().date(),
            categoria=self.cat,
            comprovante='reembolsos/fake.jpg',
            status='PENDENTE',
        )

    def test_rejeicao_com_motivo(self):
        resp = self.client.post(
            reverse('forms_pcf:reembolso_rejeitar', args=[self.pedido.pk]),
            {'observacao_adm': 'Comprovante ilegível'}
        )
        self.assertRedirects(resp, reverse('forms_pcf:reembolso_inbox'))
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'REJEITADO')
        self.assertEqual(self.pedido.observacao_adm, 'Comprovante ilegível')

    def test_rejeicao_sem_motivo_nao_rejeita(self):
        resp = self.client.post(
            reverse('forms_pcf:reembolso_rejeitar', args=[self.pedido.pk]),
            {'observacao_adm': ''}
        )
        self.assertEqual(resp.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'PENDENTE')


class ReembolsoInboxPermissionTest(TestCase):
    def _login(self, area, superuser=False):
        c = Client()
        u = User.objects.create_user(
            username=f'ui_{area}', password='pw', area=area, is_superuser=superuser
        )
        c.force_login(u)
        return c

    def test_adm_fin_tem_acesso(self):
        resp = self._login('ADM/FIN').get(reverse('forms_pcf:reembolso_inbox'))
        self.assertEqual(resp.status_code, 200)

    def test_superuser_tem_acesso(self):
        resp = self._login('MARKETING', superuser=True).get(reverse('forms_pcf:reembolso_inbox'))
        self.assertEqual(resp.status_code, 200)

    def test_outros_recebem_403(self):
        resp = self._login('MARKETING').get(reverse('forms_pcf:reembolso_inbox'))
        self.assertEqual(resp.status_code, 403)


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
