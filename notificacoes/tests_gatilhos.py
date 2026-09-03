"""Testes dos gatilhos de push espalhados por outros apps.

Separado de tests.py porque exercita sabado/, voluntario/ e supply/ — o
`manage.py test notificacoes` pega os dois arquivos.
"""
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from notificacoes.models import InscricaoPush
from sabado.models import Sabado

Voluntario = get_user_model()


@override_settings(VAPID_PRIVATE_KEY="chave-falsa", VAPID_ADMIN_EMAIL="pcf@exemplo.org")
class LembreteDisponibilidadeTest(TestCase):
    def setUp(self):
        self.ana = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123",
            area="AZUL", email="ana@exemplo.org",
        )
        InscricaoPush.objects.create(
            voluntario=self.ana, endpoint="https://push.exemplo/ana",
            p256dh="p", auth="a",
        )
        # O comando dispara quando falta 1 dia para a enquete fechar, e o
        # fechamento é 3 dias antes do sábado — ou seja, hoje + 4 dias.
        self.sabado = Sabado.objects.create(
            data=timezone.now().date() + timedelta(days=4),
            tema="Tema de teste", descricao="Descrição de teste",
        )

    @patch("notificacoes.services.webpush")
    @patch("sabado.management.commands.lembrete_disponibilidade.send_mail")
    def test_manda_push_alem_do_email(self, mock_email, mock_webpush):
        """O push SOMA ao e-mail: quem não instalou continua recebendo tudo."""
        call_command("lembrete_disponibilidade")
        mock_email.assert_called_once()
        mock_webpush.assert_called_once()

    @patch("notificacoes.services.webpush")
    @patch("sabado.management.commands.lembrete_disponibilidade.send_mail")
    def test_push_sai_mesmo_sem_email_cadastrado(self, mock_email, mock_webpush):
        """Quem não tem e-mail hoje não recebe nada; com push, passa a receber."""
        self.ana.email = ""
        self.ana.save()
        call_command("lembrete_disponibilidade")
        mock_email.assert_not_called()
        mock_webpush.assert_called_once()

    @patch("notificacoes.services.webpush")
    @patch("sabado.management.commands.lembrete_disponibilidade.send_mail")
    def test_push_leva_para_a_tela_da_enquete(self, mock_email, mock_webpush):
        call_command("lembrete_disponibilidade")
        payload = json.loads(mock_webpush.call_args.kwargs["data"])
        self.assertEqual(payload["url"], f"/sabado/responder/{self.sabado.pk}/")

    @patch("notificacoes.services.webpush")
    @patch("sabado.management.commands.lembrete_disponibilidade.send_mail")
    def test_nao_dispara_fora_da_janela(self, mock_email, mock_webpush):
        """Sábado distante não pode gerar lembrete."""
        self.sabado.data = timezone.now().date() + timedelta(days=20)
        self.sabado.save()
        call_command("lembrete_disponibilidade")
        mock_webpush.assert_not_called()


@override_settings(VAPID_PRIVATE_KEY="chave-falsa", VAPID_ADMIN_EMAIL="pcf@exemplo.org")
class OcorrenciaPushTest(TestCase):
    """Gatilho 2: ocorrências do SAAs.

    O e-mail já existente continua saindo — o push apenas soma a ele.
    """

    def setUp(self):
        self.gt = Voluntario.objects.create_user(
            username="gt", password="senha-de-teste-123", area="GESTAO_DE_TALENTOS"
        )
        self.ana = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123",
            area="AZUL", email="ana@exemplo.org",
        )
        InscricaoPush.objects.create(
            voluntario=self.ana, endpoint="https://push.exemplo/ana",
            p256dh="p", auth="a",
        )

    @patch("notificacoes.services.enviar_push_async")
    @patch("voluntario.views.threading.Thread")
    def test_criar_ocorrencia_dispara_push(self, mock_thread, mock_push):
        from django.urls import reverse

        self.client.force_login(self.gt)
        self.client.post(reverse("voluntario:criar_ocorrencia"), {
            "advertido_id": self.ana.pk,
            "regra": ["AL1"],
            "razao": ["Não respondeu o formulário"],
        })
        mock_push.assert_called_once()

    @patch("notificacoes.services.enviar_push_async")
    @patch("voluntario.views.threading.Thread")
    def test_titulo_do_push_e_generico(self, mock_thread, mock_push):
        """Notificação disciplinar aparece na tela de bloqueio, muitas vezes com
        outra pessoa olhando o celular. O título não pode entregar o assunto."""
        from django.urls import reverse

        self.client.force_login(self.gt)
        self.client.post(reverse("voluntario:criar_ocorrencia"), {
            "advertido_id": self.ana.pk,
            "regra": ["AL1"],
            "razao": ["Não respondeu o formulário"],
        })

        titulo = mock_push.call_args.args[1]
        for palavra in ("advertência", "suspensão", "alerta", "falta", "ocorrência"):
            self.assertNotIn(palavra, titulo.lower())


@override_settings(VAPID_PRIVATE_KEY="chave-falsa", VAPID_ADMIN_EMAIL="pcf@exemplo.org")
class PublicoSupplyTest(TestCase):
    """Gatilho 3: pedidos de material e reembolso.

    O público é quem cuida de material e de dinheiro — SUPPLY e ADM/FIN — e só
    quem ainda está no projeto.
    """

    @patch("notificacoes.services.webpush")
    def test_push_vai_so_para_supply_e_admfin_ativos(self, mock_webpush):
        from notificacoes.services import enviar_push

        supply = Voluntario.objects.create_user(
            username="s", password="senha-de-teste-123", area="SUPPLY"
        )
        financeiro = Voluntario.objects.create_user(
            username="f", password="senha-de-teste-123", area="ADM/FIN"
        )
        outro = Voluntario.objects.create_user(
            username="o", password="senha-de-teste-123", area="AZUL"
        )
        saiu = Voluntario.objects.create_user(
            username="x", password="senha-de-teste-123", area="SUPPLY"
        )
        saiu.data_saida = timezone.now().date()
        saiu.save()

        for v in (supply, financeiro, outro, saiu):
            InscricaoPush.objects.create(
                voluntario=v, endpoint=f"https://push.exemplo/{v.username}",
                p256dh="p", auth="a",
            )

        publico = Voluntario.objects.ativos().filter(area__in=["SUPPLY", "ADM/FIN"])
        enviar_push(publico, "Novo pedido de material", "Confira no app.")

        enviados = {
            c.kwargs["subscription_info"]["endpoint"]
            for c in mock_webpush.call_args_list
        }
        self.assertEqual(
            enviados, {"https://push.exemplo/s", "https://push.exemplo/f"}
        )
