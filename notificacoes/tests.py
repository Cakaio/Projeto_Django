import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from notificacoes.models import Aviso, InscricaoPush

# Importar do services, NÃO do pywebpush direto. O services já tem o fallback
# para quando a dependência falta (services.py:20-26); um `from pywebpush import
# ...` aqui no topo derruba o MÓDULO INTEIRO de teste no loader do unittest, e os
# 37 testes de push somem da suíte sem ninguém perceber — a suíte reporta 1 erro
# e segue verde. Foi exatamente o estado em que este arquivo estava.
from notificacoes.services import WebPushException

Voluntario = get_user_model()


def _resposta(status):
    """Objeto mínimo no formato que o pywebpush anexa à exceção."""
    class _R:
        status_code = status
    return _R()


class ManifestTest(TestCase):
    """O manifest é arquivo estático: o test client NÃO o serve (DEBUG=False na
    suíte e o handler do staticfiles não é montado). Por isso lemos do disco."""

    def setUp(self):
        caminho = finders.find("manifest.webmanifest")
        self.assertIsNotNone(caminho, "manifest.webmanifest não encontrado nos statics")
        with open(caminho, encoding="utf-8") as f:
            self.manifest = json.load(f)

    def test_manifest_e_json_valido_com_campos_obrigatorios(self):
        self.assertEqual(self.manifest["start_url"], "/inicio/")
        self.assertEqual(self.manifest["scope"], "/")
        self.assertEqual(self.manifest["display"], "standalone")

    def test_manifest_tem_icones_192_e_512(self):
        tamanhos = {i["sizes"] for i in self.manifest["icons"]}
        self.assertIn("192x192", tamanhos)
        self.assertIn("512x512", tamanhos)

    def test_manifest_tem_icone_maskable(self):
        """Sem maskable o Android recorta o ícone e decapita o logo."""
        propositos = {i.get("purpose") for i in self.manifest["icons"]}
        self.assertIn("maskable", propositos)


class ServiceWorkerTest(TestCase):
    def test_sw_servido_na_raiz_como_javascript(self):
        """Precisa ser /sw.js e não /static/js/sw.js: o escopo de um service
        worker é limitado ao próprio caminho."""
        resposta = self.client.get("/sw.js")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("javascript", resposta["Content-Type"])

    def test_sw_nao_exige_login(self):
        """O navegador busca o sw.js sem cookie de sessão em alguns momentos."""
        resposta = self.client.get("/sw.js")
        self.assertEqual(resposta.status_code, 200)


class OfflineTest(TestCase):
    def test_offline_acessivel_sem_login(self):
        """Se a sessão expirou E a rede caiu, uma página de offline atrás de
        @login_required vira redirect para um login que também não carrega."""
        resposta = self.client.get("/notificacoes/offline/")
        self.assertEqual(resposta.status_code, 200)


class ComentarioDeTemplateTest(TestCase):
    """REGRESSAO: {# #} do Django e comentario de UMA LINHA so.

    Escrito em varias linhas, o Django nao reconhece e o texto vaza para o HTML.
    Como o bloco estava no <head> do base.html, o navegador jogava a sobra para
    o topo de TODAS as telas do sistema. Para comentario multilinha o certo e
    {% comment %} ... {% endcomment %}.
    """

    def setUp(self):
        self.voluntario = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="AZUL"
        )

    def test_pagina_que_estende_base_nao_vaza_comentario(self):
        self.client.force_login(self.voluntario)
        corpo = self.client.get(reverse("notificacoes:instalar")).content.decode()
        self.assertNotIn("{#", corpo)
        self.assertNotIn("#}", corpo)

    def test_offline_nao_vaza_comentario(self):
        corpo = self.client.get(reverse("notificacoes:offline")).content.decode()
        self.assertNotIn("{#", corpo)
        self.assertNotIn("#}", corpo)


class InstalarTest(TestCase):
    def setUp(self):
        self.voluntario = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="AZUL"
        )

    def test_instalar_exige_login(self):
        resposta = self.client.get(reverse("notificacoes:instalar"))
        self.assertEqual(resposta.status_code, 302)

    def test_instalar_abre_para_voluntario_logado(self):
        self.client.force_login(self.voluntario)
        resposta = self.client.get(reverse("notificacoes:instalar"))
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "notificacoes/instalar.html")

    @override_settings(VAPID_PUBLIC_KEY="chave-publica-falsa")
    def test_com_vapid_a_tela_expoe_a_chave_publica(self):
        self.client.force_login(self.voluntario)
        resposta = self.client.get(reverse("notificacoes:instalar"))
        self.assertContains(resposta, 'data-chave="chave-publica-falsa"')

    @override_settings(VAPID_PUBLIC_KEY="")
    def test_sem_vapid_a_tela_nao_mostra_bloco_de_push(self):
        """Sem chave configurada, oferecer o botão levaria a um erro silencioso.

        A asserção olha para data-chave, e não para [data-bloco="push"]: esse
        seletor também aparece no JavaScript da página, fora do {% if %}.
        """
        self.client.force_login(self.voluntario)
        resposta = self.client.get(reverse("notificacoes:instalar"))
        self.assertNotContains(resposta, "data-chave=")


class InscricaoPushModelTest(TestCase):
    def setUp(self):
        self.ana = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="AZUL"
        )

    def test_endpoint_e_unico(self):
        """O navegador reemite o mesmo endpoint ao reinscrever — a linha tem que
        ser atualizada, nunca duplicada."""
        from django.db import IntegrityError

        from notificacoes.models import InscricaoPush

        InscricaoPush.objects.create(
            voluntario=self.ana, endpoint="https://push.exemplo/abc",
            p256dh="chave-p256", auth="chave-auth",
        )
        with self.assertRaises(IntegrityError):
            InscricaoPush.objects.create(
                voluntario=self.ana, endpoint="https://push.exemplo/abc",
                p256dh="outra", auth="outra",
            )

    def test_voluntario_pode_ter_varios_aparelhos(self):
        from notificacoes.models import InscricaoPush

        for n in range(3):
            InscricaoPush.objects.create(
                voluntario=self.ana, endpoint=f"https://push.exemplo/{n}",
                p256dh="p", auth="a",
            )
        self.assertEqual(self.ana.inscricoes_push.count(), 3)


@override_settings(VAPID_PRIVATE_KEY="chave-falsa", VAPID_ADMIN_EMAIL="pcf@exemplo.org")
class EnviarPushTest(TestCase):
    def setUp(self):
        from notificacoes.services import enviar_push
        self.enviar_push = enviar_push
        self.ana = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="AZUL"
        )

    def _inscrever(self, sufixo, voluntario=None):
        return InscricaoPush.objects.create(
            voluntario=voluntario or self.ana,
            endpoint=f"https://push.exemplo/{sufixo}",
            p256dh="p256", auth="auth",
        )

    @patch("notificacoes.services.webpush")
    def test_envia_uma_vez_por_inscricao(self, mock_webpush):
        self._inscrever("a")
        self.assertEqual(self.enviar_push([self.ana], "Oi", "Corpo"), 1)
        self.assertEqual(mock_webpush.call_count, 1)

    @patch("notificacoes.services.webpush")
    def test_voluntario_com_dois_aparelhos_recebe_duas_vezes(self, mock_webpush):
        self._inscrever("a")
        self._inscrever("b")
        self.assertEqual(self.enviar_push([self.ana], "Oi", "Corpo"), 2)
        self.assertEqual(mock_webpush.call_count, 2)

    @patch("notificacoes.services.webpush")
    def test_payload_carrega_titulo_corpo_e_url(self, mock_webpush):
        self._inscrever("a")
        self.enviar_push([self.ana], "Título", "Corpo", url="/voluntario/saas/")
        payload = json.loads(mock_webpush.call_args.kwargs["data"])
        self.assertEqual(payload["titulo"], "Título")
        self.assertEqual(payload["corpo"], "Corpo")
        self.assertEqual(payload["url"], "/voluntario/saas/")

    @patch("notificacoes.services.webpush")
    def test_410_apaga_a_inscricao(self, mock_webpush):
        """Inscrição morta: desinstalou, trocou de celular, limpou o navegador."""
        self._inscrever("morta")
        erro = WebPushException("gone")
        erro.response = _resposta(410)
        mock_webpush.side_effect = erro

        self.assertEqual(self.enviar_push([self.ana], "Oi", "Corpo"), 0)
        self.assertEqual(InscricaoPush.objects.count(), 0)

    @patch("notificacoes.services.webpush")
    def test_500_mantem_a_inscricao_e_nao_propaga(self, mock_webpush):
        """Erro do servidor de push é temporário: não pode apagar nem estourar."""
        self._inscrever("viva")
        erro = WebPushException("boom")
        erro.response = _resposta(500)
        mock_webpush.side_effect = erro

        self.assertEqual(self.enviar_push([self.ana], "Oi", "Corpo"), 0)
        self.assertEqual(InscricaoPush.objects.count(), 1)

    @patch("notificacoes.services.webpush")
    def test_falha_numa_inscricao_nao_impede_as_outras(self, mock_webpush):
        """Uma inscrição podre não pode derrubar o envio das outras 59."""
        self._inscrever("ruim")
        self._inscrever("boa")
        erro = WebPushException("boom")
        erro.response = _resposta(500)
        mock_webpush.side_effect = [erro, None]

        self.assertEqual(self.enviar_push([self.ana], "Oi", "Corpo"), 1)
        self.assertEqual(mock_webpush.call_count, 2)

    @patch("notificacoes.services.webpush")
    def test_sucesso_grava_ultimo_ok(self, mock_webpush):
        inscricao = self._inscrever("a")
        self.assertIsNone(inscricao.ultimo_ok)
        self.enviar_push([self.ana], "Oi", "Corpo")
        inscricao.refresh_from_db()
        self.assertIsNotNone(inscricao.ultimo_ok)

    @patch("notificacoes.services.webpush")
    def test_claims_vapid_sao_um_dict_novo_a_cada_envio(self, mock_webpush):
        """REGRESSÃO: o pywebpush MUTA o dict de claims que recebe (grava 'exp'
        dentro dele). Reutilizar um dict de módulo faz o primeiro envio passar e
        todos os seguintes falharem com token expirado."""
        self._inscrever("a")
        self._inscrever("b")
        self.enviar_push([self.ana], "Oi", "Corpo")

        primeiro = mock_webpush.call_args_list[0].kwargs["vapid_claims"]
        segundo = mock_webpush.call_args_list[1].kwargs["vapid_claims"]
        self.assertIsNot(primeiro, segundo)

    @patch("notificacoes.services.webpush")
    def test_sem_chave_configurada_nao_envia(self, mock_webpush):
        """Mantém dev local e a suíte funcionando sem chaves VAPID."""
        self._inscrever("a")
        with override_settings(VAPID_PRIVATE_KEY=""):
            self.assertEqual(self.enviar_push([self.ana], "Oi", "Corpo"), 0)
        mock_webpush.assert_not_called()

    @patch("notificacoes.services.webpush", None)
    def test_sem_pywebpush_instalado_desliga_o_push_sem_estourar(self):
        """REGRESSAO: o URLconf importa este modulo (urls -> views -> services).

        Um ImportError do pywebpush derrubava TODAS as rotas do site, nao so o
        push — foi o que quebrou o primeiro deploy. Com a dependencia faltando,
        o push tem que se desligar sozinho e deixar o resto do PCF de pe.
        """
        self._inscrever("a")
        self.assertEqual(self.enviar_push([self.ana], "Oi", "Corpo"), 0)

    @patch("notificacoes.services.webpush")
    def test_nao_envia_para_quem_nao_esta_na_lista(self, mock_webpush):
        bruno = Voluntario.objects.create_user(
            username="bruno", password="senha-de-teste-123", area="VERDE"
        )
        self._inscrever("ana")
        self._inscrever("bruno", voluntario=bruno)

        self.assertEqual(self.enviar_push([self.ana], "Oi", "Corpo"), 1)


class InscreverTest(TestCase):
    def setUp(self):
        self.ana = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="AZUL"
        )
        self.url = reverse("notificacoes:inscrever")
        self.corpo = {
            "endpoint": "https://push.exemplo/abc",
            "keys": {"p256dh": "chave-p256", "auth": "chave-auth"},
        }

    def _postar(self, corpo):
        return self.client.post(
            self.url, data=json.dumps(corpo), content_type="application/json"
        )

    def test_exige_login(self):
        resposta = self._postar(self.corpo)
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(InscricaoPush.objects.count(), 0)

    def test_cria_a_inscricao(self):
        self.client.force_login(self.ana)
        resposta = self._postar(self.corpo)
        self.assertEqual(resposta.status_code, 200)
        inscricao = InscricaoPush.objects.get()
        self.assertEqual(inscricao.voluntario, self.ana)
        self.assertEqual(inscricao.p256dh, "chave-p256")

    def test_mesmo_endpoint_atualiza_em_vez_de_duplicar(self):
        self.client.force_login(self.ana)
        self._postar(self.corpo)
        self.corpo["keys"]["p256dh"] = "chave-nova"
        self._postar(self.corpo)

        self.assertEqual(InscricaoPush.objects.count(), 1)
        self.assertEqual(InscricaoPush.objects.get().p256dh, "chave-nova")

    def test_sem_p256dh_da_400(self):
        self.client.force_login(self.ana)
        resposta = self._postar(
            {"endpoint": "https://push.exemplo/x", "keys": {"auth": "a"}}
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(InscricaoPush.objects.count(), 0)

    def test_grava_o_user_agent(self):
        self.client.force_login(self.ana)
        self.client.post(
            self.url, data=json.dumps(self.corpo),
            content_type="application/json", HTTP_USER_AGENT="iPhone Safari",
        )
        self.assertEqual(InscricaoPush.objects.get().user_agent, "iPhone Safari")


class DesinscreverTest(TestCase):
    def setUp(self):
        self.ana = Voluntario.objects.create_user(
            username="ana", password="senha-de-teste-123", area="AZUL"
        )
        self.bruno = Voluntario.objects.create_user(
            username="bruno", password="senha-de-teste-123", area="VERDE"
        )
        self.inscricao_do_bruno = InscricaoPush.objects.create(
            voluntario=self.bruno, endpoint="https://push.exemplo/bruno",
            p256dh="p", auth="a",
        )

    def test_nao_apaga_inscricao_de_outro_voluntario(self):
        """Sem filtrar por voluntário, um POST forjado apaga inscrição alheia."""
        self.client.force_login(self.ana)
        self.client.post(
            reverse("notificacoes:desinscrever"),
            data=json.dumps({"endpoint": "https://push.exemplo/bruno"}),
            content_type="application/json",
        )
        self.assertTrue(
            InscricaoPush.objects.filter(pk=self.inscricao_do_bruno.pk).exists()
        )

    def test_apaga_a_propria_inscricao(self):
        InscricaoPush.objects.create(
            voluntario=self.ana, endpoint="https://push.exemplo/ana",
            p256dh="p", auth="a",
        )
        self.client.force_login(self.ana)
        self.client.post(
            reverse("notificacoes:desinscrever"),
            data=json.dumps({"endpoint": "https://push.exemplo/ana"}),
            content_type="application/json",
        )
        self.assertFalse(InscricaoPush.objects.filter(voluntario=self.ana).exists())


@override_settings(VAPID_PRIVATE_KEY="chave-falsa", VAPID_ADMIN_EMAIL="pcf@exemplo.org")
class AvisosTest(TestCase):
    def setUp(self):
        self.url = reverse("notificacoes:avisos")
        self.gestor = Voluntario.objects.create_user(
            username="gestor", password="senha-de-teste-123", area="TRIADE"
        )
        self.comum = Voluntario.objects.create_user(
            username="comum", password="senha-de-teste-123", area="AZUL"
        )
        self.desligado = Voluntario.objects.create_user(
            username="desligado", password="senha-de-teste-123", area="AZUL"
        )
        self.desligado.data_saida = timezone.now().date()
        self.desligado.save()

    def _inscrever(self, voluntario):
        return InscricaoPush.objects.create(
            voluntario=voluntario,
            endpoint=f"https://push.exemplo/{voluntario.username}",
            p256dh="p", auth="a",
        )

    def test_voluntario_comum_recebe_403(self):
        self.client.force_login(self.comum)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_triade_abre(self):
        self.client.force_login(self.gestor)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    @patch("notificacoes.services.webpush")
    def test_post_cria_aviso_e_ignora_desligados(self, mock_webpush):
        """Voluntário que saiu do projeto não pode receber recado da gestão."""
        self._inscrever(self.comum)
        self._inscrever(self.desligado)

        self.client.force_login(self.gestor)
        self.client.post(self.url, {
            "titulo": "Reunião", "mensagem": "Sábado às 8h",
            "destino": "TODOS", "alvo": "",
        })

        self.assertEqual(Aviso.objects.count(), 1)
        enviados = {
            c.kwargs["subscription_info"]["endpoint"]
            for c in mock_webpush.call_args_list
        }
        self.assertNotIn("https://push.exemplo/desligado", enviados)
        self.assertIn("https://push.exemplo/comum", enviados)

    @patch("notificacoes.services.webpush")
    def test_destino_area_envia_so_para_a_area(self, mock_webpush):
        verde = Voluntario.objects.create_user(
            username="verde", password="senha-de-teste-123", area="VERDE"
        )
        self._inscrever(self.comum)
        self._inscrever(verde)

        self.client.force_login(self.gestor)
        self.client.post(self.url, {
            "titulo": "Sala Verde", "mensagem": "Recado",
            "destino": "AREA", "alvo": "VERDE",
        })

        enviados = [
            c.kwargs["subscription_info"]["endpoint"]
            for c in mock_webpush.call_args_list
        ]
        self.assertEqual(enviados, ["https://push.exemplo/verde"])

    @patch("notificacoes.services.webpush")
    def test_destino_area_sem_alvo_nao_envia(self, mock_webpush):
        """Sem área escolhida, "por área" mandaria para ninguém ou para todos —
        os dois são errados, então o form recusa."""
        self._inscrever(self.comum)
        self.client.force_login(self.gestor)
        self.client.post(self.url, {
            "titulo": "Incompleto", "mensagem": "x", "destino": "AREA", "alvo": "",
        })
        self.assertEqual(Aviso.objects.count(), 0)
        mock_webpush.assert_not_called()
