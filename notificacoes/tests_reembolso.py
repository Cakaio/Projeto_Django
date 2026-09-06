"""Gatilhos de push do reembolso — pedidos 2 e 3.

Separado de tests_gatilhos.py porque exercita forms_pcf/ inteiro e precisa de
Categoria, PedidoReembolso e do form real.

Estes testes chamam a VIEW. O teste que existia antes montava a queryset do
público dentro do próprio teste, então passava mesmo com a view mandando para o
público errado — foi por isso que o bug do SUPPLY sobreviveu tanto tempo.
"""
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from adm.models import Categoria
from forms_pcf.models import PedidoReembolso, ReceptorNotificacaoReembolso
from notificacoes.models import InscricaoPush
from notificacoes.tests_gatilhos import ThreadSincrona

Voluntario = get_user_model()


@override_settings(VAPID_PRIVATE_KEY="chave-falsa", VAPID_ADMIN_EMAIL="pcf@exemplo.org")
class ReembolsoChegouTest(TestCase):
    """Pedido 2: quando chega um pedido de reembolso, avisa a ADM."""

    def setUp(self):
        self.categoria = Categoria.objects.create(nome="Transporte", tipo="DESPESA")

        self.pediu = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="MARKETING",
            first_name="Ana", last_name="Silva")
        self.adm = Voluntario.objects.create_user(
            username="adm", password="senha-de-teste-123", area="ADM/FIN")
        self.supply = Voluntario.objects.create_user(
            username="supply", password="senha-de-teste-123", area="SUPPLY")
        self.saiu = Voluntario.objects.create_user(
            username="saiu", password="senha-de-teste-123", area="ADM/FIN")
        self.saiu.data_saida = timezone.localdate()
        self.saiu.save()

        for vol in (self.pediu, self.adm, self.supply, self.saiu):
            InscricaoPush.objects.create(
                voluntario=vol, endpoint=f"https://push.exemplo/{vol.username}",
                p256dh="p", auth="a")

        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.pediu, valor=Decimal("75.50"),
            descricao="Uber para o evento", data_gasto=timezone.localdate(),
            categoria=self.categoria,
        )

    def _disparar(self, pedido=None):
        from forms_pcf.views import EnviarReembolsoView

        with patch("notificacoes.services.threading.Thread", ThreadSincrona):
            EnviarReembolsoView()._avisar_adm_por_push(pedido or self.pedido)

    @patch("notificacoes.services.webpush")
    def test_avisa_so_quem_pode_abrir_a_caixa_de_reembolsos(self, mock_webpush):
        """SUPPLY recebia o push e tomava 403 na tela que ele prometia.

        O público agora deriva de REEMBOLSO_AREAS, a mesma constante que
        ReembolsoInboxView usa para deixar entrar.
        """
        self._disparar()
        alcancados = {c.kwargs["subscription_info"]["endpoint"]
                      for c in mock_webpush.call_args_list}
        self.assertEqual(alcancados, {"https://push.exemplo/adm"})

    @patch("notificacoes.services.webpush")
    def test_quem_recebe_e_exatamente_quem_a_view_deixa_entrar(self, mock_webpush):
        """Trava as duas pontas juntas, para não divergirem de novo."""
        from forms_pcf.views import REEMBOLSO_AREAS

        self._disparar()
        for chamada in mock_webpush.call_args_list:
            username = chamada.kwargs["subscription_info"]["endpoint"].rsplit("/", 1)[-1]
            self.assertIn(Voluntario.objects.get(username=username).area,
                          REEMBOLSO_AREAS)

    @patch("notificacoes.services.webpush")
    def test_dois_pedidos_nao_apagam_um_ao_outro_na_bandeja(self, mock_webpush):
        """Tag fixa fazia o segundo pedido substituir a notificação do primeiro."""
        outro = PedidoReembolso.objects.create(
            solicitante=self.pediu, valor=Decimal("10.00"), descricao="Outro",
            data_gasto=timezone.localdate(), categoria=self.categoria,
        )
        self._disparar()
        primeira = json.loads(mock_webpush.call_args.kwargs["data"])["tag"]
        self._disparar(outro)
        segunda = json.loads(mock_webpush.call_args.kwargs["data"])["tag"]
        self.assertNotEqual(primeira, segunda)

    @patch("notificacoes.services.webpush")
    @patch("forms_pcf.views.send_mail")
    def test_push_sai_mesmo_sem_receptor_de_email_cadastrado(
            self, mock_mail, mock_webpush):
        """O push morava depois do `return` do caminho de e-mail.

        Sem nenhum ReceptorNotificacaoReembolso ativo — que é o estado inicial
        do banco — `_enviar_email` retornava antes e a notificação nunca saía.
        """
        from forms_pcf.forms import PedidoReembolsoForm
        from forms_pcf.views import EnviarReembolsoView

        self.assertFalse(ReceptorNotificacaoReembolso.objects.exists())

        view = EnviarReembolsoView()
        view.request = RequestFactory().post("/forms/reembolso/")
        view.request.user = self.pediu

        form = PedidoReembolsoForm(data={
            "valor": "75.50",
            "descricao": "Uber",
            "data_gasto": timezone.localdate().isoformat(),
            "categoria": self.categoria.pk,
        })
        self.assertTrue(form.is_valid(), form.errors)

        with patch("notificacoes.services.threading.Thread", ThreadSincrona):
            view.form_valid(form)

        mock_mail.assert_not_called()   # nenhum receptor cadastrado
        mock_webpush.assert_called()    # mas o push saiu assim mesmo


@override_settings(VAPID_PRIVATE_KEY="chave-falsa", VAPID_ADMIN_EMAIL="pcf@exemplo.org")
class ReembolsoAprovadoTest(TestCase):
    """Pedido 3: quem teve o reembolso aprovado é avisado no celular."""

    def setUp(self):
        self.ana = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="MARKETING")
        self.outra = Voluntario.objects.create_user(
            username="outra", password="senha-de-teste-123", area="ADM/FIN")
        for vol in (self.ana, self.outra):
            InscricaoPush.objects.create(
                voluntario=vol, endpoint=f"https://push.exemplo/{vol.username}",
                p256dh="p", auth="a")

        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.ana, valor=Decimal("120.00"),
            descricao="Material de artesanato", data_gasto=timezone.localdate(),
            categoria=Categoria.objects.create(nome="Material", tipo="DESPESA"),
        )

    def _aprovar(self):
        from forms_pcf.views import avisar_solicitante_por_push

        with patch("notificacoes.services.threading.Thread", ThreadSincrona):
            avisar_solicitante_por_push(self.pedido)

    @patch("notificacoes.services.webpush")
    def test_avisa_so_quem_pediu(self, mock_webpush):
        self._aprovar()
        alcancados = {c.kwargs["subscription_info"]["endpoint"]
                      for c in mock_webpush.call_args_list}
        self.assertEqual(alcancados, {"https://push.exemplo/ana"})

    @patch("notificacoes.services.webpush")
    def test_o_texto_deixa_claro_que_aprovado_nao_e_pago(self, mock_webpush):
        """Quem lê só "aprovado" entende "o dinheiro caiu" e cobra a ADM.

        É a mesma ressalva que o e-mail de aprovação faz questão de repetir.
        """
        self._aprovar()
        corpo = json.loads(mock_webpush.call_args.kwargs["data"])["corpo"]
        self.assertIn("ainda vai sair", corpo)

    @patch("notificacoes.services.webpush")
    def test_nao_promete_aviso_no_app_quando_o_dinheiro_cair(self, mock_webpush):
        """O aviso de pagamento efetuado existe, mas é só por e-mail."""
        self._aprovar()
        corpo = json.loads(mock_webpush.call_args.kwargs["data"])["corpo"]
        self.assertIn("e-mail", corpo)

    @patch("notificacoes.services.webpush")
    def test_pedido_sem_solicitante_nao_quebra(self, mock_webpush):
        """`solicitante` é SET_NULL: pedido órfão só não tem para quem ir."""
        self.pedido.solicitante = None
        self.pedido.save()
        self._aprovar()
        mock_webpush.assert_not_called()

    @patch("notificacoes.services.webpush")
    def test_aprovar_pela_view_dispara_o_push(self, mock_webpush):
        """Prova que o gatilho está ligado na view, não só na função solta."""
        from django.contrib.messages.storage.fallback import FallbackStorage
        from forms_pcf.views import AprovarReembolsoView

        pedido = RequestFactory().post(f"/forms/reembolso/{self.pedido.pk}/aprovar/")
        pedido.user = self.outra
        pedido.session = {}
        pedido._messages = FallbackStorage(pedido)

        with patch("notificacoes.services.threading.Thread", ThreadSincrona), \
                patch("forms_pcf.views.avisar_solicitante_da_aprovacao",
                      return_value="ana@exemplo.org"):
            AprovarReembolsoView.as_view()(pedido, pk=self.pedido.pk)

        alcancados = {c.kwargs["subscription_info"]["endpoint"]
                      for c in mock_webpush.call_args_list}
        self.assertEqual(alcancados, {"https://push.exemplo/ana"})
