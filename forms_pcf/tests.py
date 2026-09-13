import io
from django.test import TestCase, Client
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal
from forms_pcf.models import FeedbackArea, PedidoReembolso, ReceptorNotificacaoReembolso
from adm.models import Categoria, Evento, Lancamento

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
            'destino': 'AREA',
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
            'destino': 'AREA',
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
            'destino': 'AREA',
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
            'destino': 'AREA',
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


class DonoDoGastoNoReembolsoTest(TestCase):
    """Nem todo gasto de quem pede e gasto da AREA de quem pede.

    Gasolina para buscar material, taxa de correio, compra que serve o projeto
    inteiro: antes tudo isso descontava o teto da salinha de quem adiantou o
    dinheiro, porque a area era preenchida automaticamente e ninguem era
    perguntado. A unica correcao possivel estava na tela de pagamento — e se a
    ADM nao lembrasse, ficava errado para sempre.
    """

    def setUp(self):
        self.client = Client()
        self.solicitante = User.objects.create_user(
            username='amarelo_vol', password='pw', area='AMARELO')
        self.client.force_login(self.solicitante)
        self.categoria = Categoria.objects.create(nome='Transporte', tipo='DESPESA')
        self.evento = Evento.objects.create(nome='Festa Junina 2026', ativo=True)

    def _enviar(self, **extras):
        dados = {
            'valor': '87.40',
            'descricao': 'gasolina para buscar material',
            'data_gasto': timezone.localdate().isoformat(),
            'categoria': self.categoria.pk,
            'destino': 'AREA',
        }
        dados.update(extras)
        with patch('forms_pcf.views.send_mail'):
            resposta = self.client.post(reverse('forms_pcf:reembolso'), dados)
        return resposta, PedidoReembolso.objects.order_by('-pk').first()

    def test_padrao_continua_sendo_a_area_de_quem_pede(self):
        _, pedido = self._enviar()
        self.assertEqual(pedido.area, 'AMARELO')
        self.assertIsNone(pedido.evento)

    def test_gasto_de_evento_nao_desconta_area_nenhuma(self):
        """Gasolina da Festa Junina nao e gasto do Amarelo — nem da equipe de
        Eventos, que e um time e nao o evento."""
        _, pedido = self._enviar(destino='EVENTO', evento=self.evento.pk)
        self.assertEqual(pedido.evento, self.evento)
        self.assertEqual(pedido.area, '')

    def test_gasto_do_projeto_nao_desconta_area_nenhuma(self):
        _, pedido = self._enviar(destino='GERAL')
        self.assertEqual(pedido.area, '')
        self.assertIsNone(pedido.evento)

    def test_evento_e_obrigatorio_quando_a_escolha_e_evento(self):
        """Direto no formulário: a resposta de erro renderiza template, e o
        test client quebra ao copiar o contexto neste ambiente."""
        from forms_pcf.forms import PedidoReembolsoForm
        formulario = PedidoReembolsoForm({
            'valor': '87.40', 'descricao': 'gasolina',
            'data_gasto': timezone.localdate().isoformat(),
            'categoria': self.categoria.pk, 'destino': 'EVENTO', 'evento': '',
        }, voluntario=self.solicitante)
        self.assertFalse(formulario.is_valid())
        self.assertIn('evento', formulario.errors)

    def test_evento_escolhido_por_engano_some_quando_o_destino_e_outro(self):
        """O radio muda, o select fica preenchido. Sem limpar, o pedido sairia
        marcado com um evento que a pessoa nao quis."""
        _, pedido = self._enviar(destino='AREA', evento=self.evento.pk)
        self.assertIsNone(pedido.evento)
        self.assertEqual(pedido.area, 'AMARELO')

    def test_gasto_geral_aprovado_nao_entra_em_teto_nenhum(self):
        """O encontro das pontas: sem area, nao ha teto contra o que comparar."""
        from adm.models import TetoArea
        from adm.servicos import situacao_dos_tetos
        TetoArea.objects.create(area='AMARELO', valor='500.00')
        _, pedido = self._enviar(destino='GERAL')

        adm = User.objects.create_user(username='adm_geral', password='pw', area='ADM/FIN')
        self.client.force_login(adm)
        with patch('forms_pcf.views.send_mail'):
            self.client.post(reverse('forms_pcf:reembolso_aprovar', args=[pedido.pk]))

        linha = next(l for l in situacao_dos_tetos(timezone.localdate())
                     if l['area'] == 'AMARELO')
        self.assertEqual(linha['gasto'], Decimal('0'))


class AdmEscolheAreaNaAprovacaoTest(TestCase):
    """O lancamento nasce na APROVACAO, entao e la que a area precisa estar
    certa. Antes so dava para corrigir no pagamento: entre aprovar e pagar, o
    teto da area errada ficava encolhido, e se a ADM esquecesse, para sempre.
    """

    def setUp(self):
        self.client = Client()
        self.adm = User.objects.create_user(username='adm_apr', password='pw', area='ADM/FIN')
        self.solicitante = User.objects.create_user(
            username='vol_apr', password='pw', area='AMARELO')
        self.categoria = Categoria.objects.create(nome='Transporte', tipo='DESPESA')
        self.evento = Evento.objects.create(nome='Festa Junina 2026', ativo=True)
        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.solicitante, valor=Decimal('87.40'),
            descricao='gasolina', data_gasto=timezone.localdate(),
            categoria=self.categoria, status='PENDENTE', area='AMARELO',
        )
        self.client.force_login(self.adm)

    def _aprovar(self, **dados):
        with patch('forms_pcf.views.send_mail'):
            return self.client.post(
                reverse('forms_pcf:reembolso_aprovar', args=[self.pedido.pk]), dados)

    def test_adm_corrige_a_area_na_aprovacao(self):
        self._aprovar(area='SUPPLY')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.area, 'SUPPLY')
        self.assertEqual(self.pedido.lancamento.area, 'SUPPLY')

    def test_adm_tira_a_area_na_aprovacao(self):
        self._aprovar(area='')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.area, '')
        self.assertEqual(self.pedido.lancamento.area, '')

    def test_adm_marca_evento_na_aprovacao(self):
        self._aprovar(area='', evento=self.evento.pk)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.evento, self.evento)
        self.assertEqual(self.pedido.lancamento.evento, self.evento)

    def test_aprovar_sem_mexer_mantem_o_que_o_pedido_trouxe(self):
        """O botao de aprovar sozinho, sem tocar nos selects, nao pode limpar a
        area que o solicitante escolheu."""
        self._aprovar()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.area, 'AMARELO')
        self.assertEqual(self.pedido.lancamento.area, 'AMARELO')

    def test_area_invalida_no_post_nao_e_gravada(self):
        self._aprovar(area='NAO_EXISTE')
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.area, 'AMARELO')

    def test_data_do_lancamento_usa_o_fuso_de_sao_paulo(self):
        """`timezone.now().date()` e UTC: depois das 21h em Sao Paulo ele ja
        virou o dia seguinte, e numa virada de semestre isso joga o reembolso
        no semestre errado."""
        from datetime import date, datetime, timezone as tz
        with patch('forms_pcf.views.timezone.localdate', return_value=date(2026, 6, 30)), \
             patch('forms_pcf.views.timezone.now',
                   return_value=datetime(2026, 7, 1, 1, 0, tzinfo=tz.utc)):
            self._aprovar()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.lancamento.data, date(2026, 6, 30))


class TelasDoDonoDoGastoTest(TestCase):
    """As duas telas de verdade, renderizadas.

    RequestFactory, nao o Client: o test client quebra ao copiar o contexto do
    template neste ambiente (Python 3.14).
    """

    def setUp(self):
        from django.test import RequestFactory
        self.fabrica = RequestFactory()
        self.categoria = Categoria.objects.create(nome='Transporte', tipo='DESPESA')
        self.evento = Evento.objects.create(nome='Festa Junina 2026', ativo=True)
        Evento.objects.create(nome='Evento encerrado', ativo=False)
        self.solicitante = User.objects.create_user(
            username='amarelo_tela', password='pw', area='AMARELO')
        self.adm = User.objects.create_user(
            username='adm_tela', password='pw', area='ADM/FIN')

    def _pedir(self, url, usuario):
        requisicao = self.fabrica.get(url)
        requisicao.user = usuario
        return requisicao

    def test_formulario_pergunta_de_quem_e_o_gasto(self):
        from forms_pcf.views import EnviarReembolsoView
        resposta = EnviarReembolsoView.as_view()(
            self._pedir('/forms/reembolso/', self.solicitante))
        html = resposta.rendered_content
        self.assertIn('name="destino"', html)
        self.assertIn('Da minha área — Amarelo', html)
        self.assertIn('Do projeto em geral', html)
        # Evento inativo nao pode ser oferecido: o gasto iria parar num evento
        # que ninguem acompanha mais.
        self.assertIn('Festa Junina 2026', html)
        self.assertNotIn('Evento encerrado', html)

    def test_caixa_da_adm_deixa_escolher_area_e_evento_ao_aprovar(self):
        from forms_pcf.views import ReembolsoInboxView
        pedido = PedidoReembolso.objects.create(
            solicitante=self.solicitante, valor=Decimal('87.40'),
            descricao='gasolina', data_gasto=timezone.localdate(),
            categoria=self.categoria, status='PENDENTE', area='AMARELO',
        )
        resposta = ReembolsoInboxView.as_view()(
            self._pedir('/forms/reembolsos/', self.adm))
        html = resposta.rendered_content
        self.assertIn(f'name="area"', html)
        self.assertIn(f'id="evento-{pedido.pk}"', html)
        # A area do pedido ja vem marcada, senao aprovar sem mexer a apagaria.
        self.assertIn('<option value="AMARELO" selected>Amarelo</option>', html)

    def test_a_coluna_mostra_o_dono_do_gasto_e_nao_a_area_de_quem_pediu(self):
        from forms_pcf.views import ReembolsoInboxView
        PedidoReembolso.objects.create(
            solicitante=self.solicitante, valor=Decimal('87.40'),
            descricao='gasolina do passeio', data_gasto=timezone.localdate(),
            categoria=self.categoria, status='PENDENTE', area='', evento=self.evento,
        )
        html = ReembolsoInboxView.as_view()(
            self._pedir('/forms/reembolsos/', self.adm)).rendered_content
        self.assertIn('Festa Junina 2026', html)
