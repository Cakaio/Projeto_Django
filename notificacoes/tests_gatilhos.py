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


class ThreadSincrona:
    """Thread falsa que roda o alvo na hora, em vez de em paralelo.

    `enviar_push_async` sobe uma thread daemon; num teste isso é corrida — a
    asserção roda antes do envio. Trocar a Thread por esta faz o caminho inteiro
    (montagem do payload, filtro de inscrições, chamada do webpush) executar
    de forma síncrona e determinística, sem precisar dublar o serviço e perder
    justamente o que se quer verificar: o texto que chega no aparelho.
    """

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target, self._args = target, args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


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
        # O comando agora cobra TODO DIA enquanto a enquete estiver aberta, e a
        # enquete fecha um dia antes do sábado (Sabado.enquete_aberta). Qualquer
        # data futura com folga serve; +4 dias é uma terça para um sábado.
        self.sabado = Sabado.objects.create(
            data=timezone.localdate() + timedelta(days=4),
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
    def test_cobra_todo_dia_enquanto_a_enquete_estiver_aberta(
            self, mock_email, mock_webpush):
        """A cobrança é diária — antes saía num único dia por sábado.

        Este teste substitui o antigo `test_nao_dispara_fora_da_janela`, que
        afirmava que um sábado a 20 dias NÃO gera lembrete. Isso era verdade
        quando o disparo era uma igualdade exata (`hoje == data - 4 dias`) e
        deixou de ser: o pedido é cobrar todo dia até fechar.
        """
        self.sabado.data = timezone.localdate() + timedelta(days=20)
        self.sabado.save()
        call_command("lembrete_disponibilidade")
        mock_webpush.assert_called_once()

    @patch("notificacoes.services.webpush")
    @patch("sabado.management.commands.lembrete_disponibilidade.send_mail")
    def test_nao_cobra_depois_que_a_enquete_fecha(self, mock_email, mock_webpush):
        """Enquete fechada (véspera do sábado) não gera cobrança nenhuma."""
        self.sabado.data = timezone.localdate() + timedelta(days=1)
        self.sabado.save()
        call_command("lembrete_disponibilidade")
        mock_webpush.assert_not_called()
        mock_email.assert_not_called()

    @patch("notificacoes.services.webpush")
    @patch("sabado.management.commands.lembrete_disponibilidade.send_mail")
    def test_nao_cobra_sabado_que_ja_passou(self, mock_email, mock_webpush):
        """Sábado no passado não pode gerar cobrança."""
        self.sabado.data = timezone.localdate() - timedelta(days=7)
        self.sabado.save()
        call_command("lembrete_disponibilidade")
        mock_webpush.assert_not_called()

    @patch("notificacoes.services.webpush")
    @patch("sabado.management.commands.lembrete_disponibilidade.send_mail")
    def test_nao_cobra_quem_ja_respondeu(self, mock_email, mock_webpush):
        from sabado.models import DisponibilidadeVoluntario
        DisponibilidadeVoluntario.objects.create(
            sabado=self.sabado, voluntario=self.ana, vai_ao_projeto=True)
        call_command("lembrete_disponibilidade")
        mock_webpush.assert_not_called()

    @patch("notificacoes.services.webpush")
    @patch("sabado.management.commands.lembrete_disponibilidade.send_mail")
    def test_cobra_um_sabado_so_mesmo_com_varios_abertos(
            self, mock_email, mock_webpush):
        """Vários sábados cadastrados não podem virar vários pushes por dia.

        O seed do projeto cria dez sábados de uma vez; sem esta trava, cada
        pessoa receberia uma notificação POR SÁBADO ABERTO, POR DIA.
        """
        for adiante in (11, 18, 25):
            Sabado.objects.create(
                data=timezone.localdate() + timedelta(days=adiante),
                tema="Outro", descricao="Outro",
            )
        call_command("lembrete_disponibilidade")
        mock_webpush.assert_called_once()
        payload = json.loads(mock_webpush.call_args.kwargs["data"])
        # O mais próximo, não um qualquer.
        self.assertEqual(payload["url"], f"/sabado/responder/{self.sabado.pk}/")

    @patch("notificacoes.services.webpush")
    @patch("sabado.management.commands.lembrete_disponibilidade.send_mail")
    def test_dry_run_nao_envia_nada(self, mock_email, mock_webpush):
        call_command("lembrete_disponibilidade", "--dry-run")
        mock_webpush.assert_not_called()
        mock_email.assert_not_called()

    @patch("notificacoes.services.webpush")
    @patch("sabado.management.commands.lembrete_disponibilidade.send_mail")
    def test_texto_nao_diz_fecha_amanha_quando_faltam_dias(
            self, mock_email, mock_webpush):
        """O texto antigo dizia "fecha amanhã" todo dia — mentira em quase todos.

        Com o sábado a 4 dias, faltam 3 dias para o fechamento.
        """
        call_command("lembrete_disponibilidade")
        payload = json.loads(mock_webpush.call_args.kwargs["data"])
        self.assertNotIn("amanhã", payload["corpo"])
        self.assertIn("3 dias", payload["corpo"])

    @patch("notificacoes.services.webpush")
    def test_falha_de_email_nao_impede_o_push(self, mock_webpush):
        """Um endereço ruim não pode calar a notificação de todo mundo.

        Antes o laço de e-mail usava fail_silently=False e vinha ANTES do push:
        uma exceção no meio dele derrubava o comando e o push não saía para
        ninguém. Num comando diário isso vira falha recorrente.
        """
        with patch("sabado.management.commands.lembrete_disponibilidade.send_mail",
                   side_effect=OSError("SMTP fora do ar")):
            call_command("lembrete_disponibilidade")
        mock_webpush.assert_called_once()


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


@override_settings(VAPID_PRIVATE_KEY="chave-falsa", VAPID_ADMIN_EMAIL="pcf@exemplo.org")
class AberturaDaEnqueteTest(TestCase):
    """Pedido 1a: cadastrar o sábado no admin avisa a equipe.

    O gatilho vive em `SabadoAdmin.save_model` e não num signal `post_save`
    porque o admin é o único caminho de escrita de Sabado em produção — um
    signal pegaria também o seed (dez sábados de uma vez) e as dezenas de
    criações espalhadas pelos testes de outros apps.
    """

    def setUp(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from sabado.admin import SabadoAdmin

        self.admin = SabadoAdmin(Sabado, AdminSite())
        self.request = RequestFactory().post("/admin/sabado/sabado/add/")

        self.ana = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="AZUL")
        self.saiu = Voluntario.objects.create_user(
            username="saiu", password="senha-de-teste-123", area="AZUL")
        self.saiu.data_saida = timezone.localdate()
        self.saiu.save()
        for vol in (self.ana, self.saiu):
            InscricaoPush.objects.create(
                voluntario=vol, endpoint=f"https://push.exemplo/{vol.username}",
                p256dh="p", auth="a")

    def _salvar(self, sabado, change=False):
        # Thread síncrona: sem isto a asserção corre contra a thread daemon do
        # enviar_push_async e o teste vira moeda ao ar.
        with patch("notificacoes.services.threading.Thread", ThreadSincrona):
            self.admin.save_model(self.request, sabado, form=None, change=change)

    @patch("notificacoes.services.webpush")
    def test_cadastrar_sabado_avisa_os_voluntarios_ativos(self, mock_webpush):
        sabado = Sabado(data=timezone.localdate() + timedelta(days=6),
                        tema="Gratidão", descricao="d")
        self._salvar(sabado)
        alcancados = {c.kwargs["subscription_info"]["endpoint"]
                      for c in mock_webpush.call_args_list}
        # Quem saiu do projeto não recebe cobrança de enquete que não é dele.
        self.assertEqual(alcancados, {"https://push.exemplo/ana"})

    @patch("notificacoes.services.webpush")
    def test_o_texto_cita_a_data_e_o_tema(self, mock_webpush):
        sabado = Sabado(data=timezone.localdate() + timedelta(days=6),
                        tema="Gratidão", descricao="d")
        self._salvar(sabado)
        payload = json.loads(mock_webpush.call_args.kwargs["data"])
        self.assertIn("Gratidão", payload["corpo"])
        self.assertEqual(payload["url"], f"/sabado/responder/{sabado.pk}/")

    @patch("notificacoes.services.webpush")
    def test_sabado_sem_tema_nao_deixa_buraco_no_texto(self, mock_webpush):
        sabado = Sabado(data=timezone.localdate() + timedelta(days=6),
                        tema="", descricao="")
        self._salvar(sabado)
        payload = json.loads(mock_webpush.call_args.kwargs["data"])
        self.assertNotIn("—  ", payload["corpo"])
        self.assertTrue(payload["corpo"].strip())

    @patch("notificacoes.services.webpush")
    def test_editar_sabado_existente_nao_avisa_de_novo(self, mock_webpush):
        sabado = Sabado.objects.create(
            data=timezone.localdate() + timedelta(days=6), tema="a", descricao="d")
        self._salvar(sabado, change=True)
        mock_webpush.assert_not_called()

    @patch("notificacoes.services.webpush")
    def test_cadastrar_sabado_ja_fechado_nao_avisa(self, mock_webpush):
        """Cadastrar retroativamente não convoca ninguém para responder."""
        sabado = Sabado(data=timezone.localdate(), tema="a", descricao="d")
        self._salvar(sabado)
        mock_webpush.assert_not_called()


class AbrirEnqueteNaoContaComoRespostaTest(TestCase):
    """Só ABRIR a tela da enquete não pode marcar a pessoa como respondente.

    Antes a view fazia get_or_create no GET, então o push do lembrete levava a
    pessoa à tela, ela olhava, fechava sem enviar — e sumia da fila de cobrança
    daquele sábado, ainda contada como "não vai ao projeto". Quanto melhor a
    notificação funcionasse, mais gente o bug engoliria.
    """

    def setUp(self):
        from django.test import RequestFactory

        self.factory = RequestFactory()
        self.ana = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="AZUL")
        self.sabado = Sabado.objects.create(
            data=timezone.localdate() + timedelta(days=5),
            tema="Tema", descricao="d")

    def test_get_nao_grava_resposta(self):
        from sabado.models import DisponibilidadeVoluntario
        from sabado.views import responder_disponibilidade

        pedido = self.factory.get(f"/sabado/responder/{self.sabado.pk}/")
        pedido.user = self.ana
        responder_disponibilidade(pedido, self.sabado.pk)

        self.assertFalse(
            DisponibilidadeVoluntario.objects.filter(
                sabado=self.sabado, voluntario=self.ana).exists())

    def test_quem_so_abriu_continua_na_fila_de_cobranca(self):
        from sabado.notificacoes import quem_nao_respondeu
        from sabado.views import responder_disponibilidade

        pedido = self.factory.get(f"/sabado/responder/{self.sabado.pk}/")
        pedido.user = self.ana
        responder_disponibilidade(pedido, self.sabado.pk)

        self.assertIn(self.ana, quem_nao_respondeu(self.sabado))
