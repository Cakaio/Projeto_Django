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

    @patch('forms_pcf.views.send_mail')
    def test_sem_comprovante_o_pedido_entra_do_mesmo_jeito(self, mock_mail):
        """Anexar é opcional: quem decide se o pedido vale sem comprovante é a
        ADM/Fin, na aprovação.

        Antes o formulário barrava, e gasto sem nota — estacionamento, feira,
        troco de ônibus — simplesmente não era pedido.
        """
        self.client.post(reverse('forms_pcf:reembolso'), {
            'valor': '10.00',
            'descricao': 'Estacionamento, sem nota',
            'data_gasto': timezone.now().date().isoformat(),
            'categoria': self.cat.pk,
        })
        pedido = PedidoReembolso.objects.get()
        self.assertEqual(pedido.status, 'PENDENTE')
        self.assertFalse(pedido.comprovante)

    def test_valor_continua_obrigatorio(self):
        """Opcional é o comprovante, não o resto: pedido sem valor não é pedido.

        Exercita o FORMULÁRIO, não a view: um POST inválido faz a view
        re-renderizar a página, e o test client quebra ao instrumentar template
        no Python 3.14. A regra sob teste é do formulário de qualquer forma.
        """
        from forms_pcf.forms import PedidoReembolsoForm

        form = PedidoReembolsoForm({
            'descricao': 'Sem valor',
            'data_gasto': timezone.now().date().isoformat(),
            'categoria': self.cat.pk,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('valor', form.errors)
        self.assertNotIn('comprovante', form.errors)


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

    def _pedido_de_outra_pessoa(self, email='vol@pcf.org'):
        solicitante = User.objects.create_user(
            username='vol_aprov', password='pw', area='RECREACAO', email=email,
        )
        return PedidoReembolso.objects.create(
            solicitante=solicitante,
            valor=Decimal('80.00'),
            descricao='Tinta',
            data_gasto=timezone.now().date(),
            categoria=self.cat,
            comprovante='reembolsos/fake.jpg',
            status='PENDENTE',
        )

    def test_aprovacao_avisa_o_solicitante_por_email(self):
        """Antes a pessoa não sabia da aprovação: só descobria pelo e-mail de
        pagamento, dias depois, ou não descobria."""
        from django.core import mail

        pedido = self._pedido_de_outra_pessoa()
        self.client.post(reverse('forms_pcf:reembolso_aprovar', args=[pedido.pk]))

        self.assertEqual(len(mail.outbox), 1)
        enviado = mail.outbox[0]
        self.assertEqual(enviado.to, ['vol@pcf.org'])
        self.assertIn('aprovado', enviado.subject.lower())
        self.assertIn('80.00', enviado.body)
        self.assertIn('Tinta', enviado.body)

    def test_o_email_deixa_claro_que_aprovado_ainda_nao_e_pago(self):
        """Quem lê "aprovado" e entende "o dinheiro caiu" cobra a ADM por um
        pagamento que ninguém prometeu para hoje."""
        from django.core import mail

        pedido = self._pedido_de_outra_pessoa()
        self.client.post(reverse('forms_pcf:reembolso_aprovar', args=[pedido.pk]))

        self.assertIn('ainda vai ser feito', mail.outbox[0].body)

    def test_solicitante_sem_email_nao_impede_a_aprovacao(self):
        from django.core import mail

        pedido = self._pedido_de_outra_pessoa(email='')
        self.client.post(reverse('forms_pcf:reembolso_aprovar', args=[pedido.pk]))

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'APROVADO')
        self.assertEqual(len(mail.outbox), 0)

    @patch('forms_pcf.views.send_mail', side_effect=Exception('SMTP fora do ar'))
    def test_falha_no_envio_nao_desfaz_a_aprovacao(self, mock_mail):
        """A aprovação já está no banco; e-mail que não sai não pode revogá-la."""
        pedido = self._pedido_de_outra_pessoa()
        self.client.post(reverse('forms_pcf:reembolso_aprovar', args=[pedido.pk]))

        pedido.refresh_from_db()
        self.assertEqual(pedido.status, 'APROVADO')
        self.assertIsNotNone(pedido.lancamento)

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


class ReembolsoSemComprovanteTest(TestCase):
    """Comprovante opcional muda o que a ADM precisa VER para decidir."""

    def setUp(self):
        from django.test import RequestFactory
        self.fabrica = RequestFactory()
        self.adm = User.objects.create_user(
            username='fin', password='pw', area='ADM/FIN')
        self.solicitante = User.objects.create_user(
            username='vol', password='pw', area='RECREACAO', first_name='Ana')
        self.cat = Categoria.objects.create(nome='Transporte', tipo='DESPESA')
        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.solicitante, valor=Decimal('18.00'),
            descricao='Estacionamento, sem nota',
            data_gasto=timezone.now().date(), categoria=self.cat,
            status='PENDENTE',
        )

    def _inbox(self):
        from forms_pcf.views import ReembolsoInboxView
        pedido = self.fabrica.get(reverse('forms_pcf:reembolso_inbox'))
        pedido.user = self.adm
        return ReembolsoInboxView.as_view()(pedido).render().content.decode()

    def test_o_pedido_existe_sem_arquivo(self):
        self.assertFalse(self.pedido.comprovante)

    def test_a_caixa_de_entrada_avisa_que_falta_comprovante(self):
        """Antes aparecia só um traço. Discreto demais para uma ausência que
        muda a decisão de aprovar."""
        html = self._inbox()
        self.assertIn('sem comprovante', html)

    def test_a_adm_consegue_aprovar_sem_comprovante(self):
        """É o ponto do pedido: a ADM aceita tendo ou não tendo o arquivo."""
        from django.contrib.messages.storage.fallback import FallbackStorage
        from forms_pcf.views import AprovarReembolsoView

        requisicao = self.fabrica.post(
            reverse('forms_pcf:reembolso_aprovar', args=[self.pedido.pk]))
        requisicao.user = self.adm
        requisicao.session = {}
        requisicao._messages = FallbackStorage(requisicao)

        with patch('forms_pcf.views.send_mail'):
            resposta = AprovarReembolsoView.as_view()(requisicao, pk=self.pedido.pk)

        self.assertEqual(resposta.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'APROVADO')
        self.assertIsNotNone(self.pedido.lancamento)
