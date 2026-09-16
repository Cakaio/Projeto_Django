"""Entrar com a conta Google da organização.

O que estes testes protegem não é conveniência, é a porta de entrada do
sistema. Um erro aqui deixa alguém de fora do projeto entrar como voluntário —
e o sistema tem ficha de criança dentro.
"""
import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from voluntario import google_login
from voluntario.google_login import LoginGoogleInvalido

Voluntario = get_user_model()

DOMINIO = 'projetocriancafeliz.org'
CONFIG = dict(GOOGLE_LOGIN_CLIENT_ID='id-de-teste.apps.googleusercontent.com',
              GOOGLE_LOGIN_DOMINIO=DOMINIO)


def carga(**extras):
    """O que o Google devolve num token válido da organização."""
    dados = {
        'email': 'ana@projetocriancafeliz.org',
        'email_verified': True,
        'hd': DOMINIO,
        'given_name': 'Ana',
        'family_name': 'Souza',
        'sub': '1234567890',
    }
    dados.update(extras)
    return dados


@override_settings(**CONFIG)
class VerificacaoDoTokenTests(TestCase):
    """Nada do que o navegador afirma é aceito: quem valida é o Google."""

    def _verificar(self, devolvido):
        with patch('voluntario.google_login.id_token.verify_oauth2_token',
                   return_value=devolvido):
            return google_login.verificar_credencial('token-qualquer')

    def test_token_da_organizacao_passa(self):
        dados = self._verificar(carga())
        self.assertEqual(dados['email'], 'ana@projetocriancafeliz.org')

    def test_dominio_diferente_e_recusado(self):
        """Uma conta Workspace de OUTRA organização também traz `hd`."""
        with self.assertRaises(LoginGoogleInvalido):
            self._verificar(carga(hd='outraong.org', email='ana@outraong.org'))

    def test_gmail_comum_e_recusado(self):
        """Gmail pessoal não tem `hd`."""
        with self.assertRaises(LoginGoogleInvalido):
            self._verificar(carga(hd=None, email='ana@gmail.com'))

    def test_email_do_dominio_sem_hd_e_recusado(self):
        """O caso perigoso: o e-mail TERMINA com o domínio, mas a conta não é
        Workspace. Conferir só o final do e-mail deixaria isso entrar."""
        with self.assertRaises(LoginGoogleInvalido):
            self._verificar(carga(hd=None))

    def test_email_nao_verificado_e_recusado(self):
        with self.assertRaises(LoginGoogleInvalido):
            self._verificar(carga(email_verified=False))

    def test_token_invalido_vira_recusa_e_nao_estouro(self):
        """`verify_oauth2_token` levanta ValueError para assinatura errada,
        token vencido ou `aud` de outro app. O voluntário não pode ver um 500."""
        with patch('voluntario.google_login.id_token.verify_oauth2_token',
                   side_effect=ValueError('token vencido')):
            with self.assertRaises(LoginGoogleInvalido):
                google_login.verificar_credencial('token-podre')

    def test_sem_client_id_configurado_recusa(self):
        with override_settings(GOOGLE_LOGIN_CLIENT_ID=''):
            with self.assertRaises(LoginGoogleInvalido):
                google_login.verificar_credencial('qualquer')


@override_settings(**CONFIG)
class QuemEntraTests(TestCase):

    def test_voluntario_existente_casa_pelo_email(self):
        ana = Voluntario.objects.create_user(
            username='ana', password='x', area='MARKETING',
            email='ana@projetocriancafeliz.org')

        achado, criado = google_login.voluntario_para(carga())

        self.assertEqual(achado.pk, ana.pk)
        self.assertFalse(criado)
        self.assertEqual(Voluntario.objects.count(), 1)

    def test_casa_sem_diferenciar_maiuscula(self):
        ana = Voluntario.objects.create_user(
            username='ana', password='x', area='MARKETING',
            email='Ana@ProjetoCriancaFeliz.org')

        achado, _ = google_login.voluntario_para(carga())

        self.assertEqual(achado.pk, ana.pk)

    def test_primeira_entrada_cria_ativo_sem_area(self):
        """Decisão da coordenação: entra e usa, mas sem permissão de área
        nenhuma até a Gestão de Talentos completar o cadastro."""
        novo, criado = google_login.voluntario_para(carga())

        self.assertTrue(criado)
        self.assertTrue(novo.is_active)
        self.assertIsNone(novo.data_saida)
        self.assertEqual(novo.area, '')
        self.assertEqual(novo.first_name, 'Ana')
        self.assertEqual(novo.last_name, 'Souza')

    def test_quem_nasce_pelo_google_nao_tem_senha_utilizavel(self):
        """Conta sem senha definida não pode virar porta de força bruta."""
        novo, _ = google_login.voluntario_para(carga())
        self.assertFalse(novo.has_usable_password())

    def test_username_colidido_ganha_sufixo(self):
        Voluntario.objects.create_user(username='ana', password='x',
                                       area='MARKETING', email='outra@x.org')

        novo, _ = google_login.voluntario_para(carga())

        self.assertNotEqual(novo.username, 'ana')
        self.assertTrue(novo.username.startswith('ana'))

    def test_dois_cadastros_com_o_mesmo_email_recusam_o_login(self):
        """Login ambíguo é pior que login negado: entrar na conta errada dá
        acesso ao que aquela pessoa podia ver."""
        for nome in ('ana1', 'ana2'):
            Voluntario.objects.create_user(
                username=nome, password='x', area='MARKETING',
                email='ana@projetocriancafeliz.org')

        with self.assertRaises(LoginGoogleInvalido):
            google_login.voluntario_para(carga())

    def test_quem_saiu_do_projeto_nao_entra(self):
        """`data_saida` preenchido é ex-voluntário. O Google continua
        autenticando a pessoa; quem decide o acesso é o cadastro."""
        Voluntario.objects.create_user(
            username='ana', password='x', area='MARKETING',
            email='ana@projetocriancafeliz.org',
            data_saida=datetime.date(2026, 1, 1))

        with self.assertRaises(LoginGoogleInvalido):
            google_login.voluntario_para(carga())

    def test_conta_bloqueada_nao_entra(self):
        Voluntario.objects.create_user(
            username='ana', password='x', area='MARKETING',
            email='ana@projetocriancafeliz.org', is_active=False)

        with self.assertRaises(LoginGoogleInvalido):
            google_login.voluntario_para(carga())


class ConfiguracaoTests(TestCase):

    @override_settings(**CONFIG)
    def test_configurado_quando_ha_client_id(self):
        self.assertTrue(google_login.configurado())

    @override_settings(GOOGLE_LOGIN_CLIENT_ID='', GOOGLE_LOGIN_DOMINIO=DOMINIO)
    def test_sem_client_id_nao_esta_configurado(self):
        """Máquina sem a chave não pode quebrar: o botão só não aparece."""
        self.assertFalse(google_login.configurado())


@override_settings(**CONFIG)
class ViewDeEntradaTests(TestCase):
    """A porta propriamente dita."""

    def setUp(self):
        from django.test import RequestFactory
        self.fabrica = RequestFactory()

    def _entrar(self, credencial='token', devolvido=None, erro=None):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from voluntario.views import entrar_com_google

        pedido = self.fabrica.post('/login/google/', {'credential': credencial})
        pedido.user = None
        pedido.session = self.client.session
        pedido._messages = FallbackStorage(pedido)

        alvo = 'voluntario.google_login.id_token.verify_oauth2_token'
        with patch(alvo, return_value=devolvido, side_effect=erro):
            return pedido, entrar_com_google(pedido)

    def test_conta_da_organizacao_entra(self):
        Voluntario.objects.create_user(
            username='ana', password='x', area='MARKETING',
            email='ana@projetocriancafeliz.org')

        pedido, resposta = self._entrar(devolvido=carga())

        self.assertEqual(resposta.status_code, 302)
        self.assertIn('_auth_user_id', pedido.session)

    def test_conta_de_fora_nao_entra_e_volta_para_o_login(self):
        pedido, resposta = self._entrar(
            devolvido=carga(hd='outraong.org', email='x@outraong.org'))

        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/login/', resposta.url)
        self.assertNotIn('_auth_user_id', pedido.session)

    def test_primeira_entrada_avisa_para_procurar_a_gt(self):
        from django.contrib.messages import get_messages

        pedido, _ = self._entrar(devolvido=carga())

        recados = ' '.join(str(m) for m in get_messages(pedido))
        self.assertIn('Gestão de Talentos', recados)
        self.assertTrue(Voluntario.objects.filter(
            email='ana@projetocriancafeliz.org').exists())

    def test_get_nao_entra(self):
        """Entrar muda estado: não pode acontecer por abrir uma URL."""
        from django.http import HttpResponseNotAllowed
        from voluntario.views import entrar_com_google

        pedido = self.fabrica.get('/login/google/')
        self.assertIsInstance(entrar_com_google(pedido), HttpResponseNotAllowed)

    def test_post_sem_credencial_nao_estoura(self):
        pedido, resposta = self._entrar(credencial='', devolvido=carga())
        self.assertEqual(resposta.status_code, 302)
        self.assertNotIn('_auth_user_id', pedido.session)


class TelaDeLoginTests(TestCase):
    """O botão, e o recado que o botão precisa poder mostrar."""

    def _pedido(self):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory
        pedido = RequestFactory().get('/login/')
        pedido.session = self.client.session
        # LoginView com redirect_authenticated_user lê request.user, e o
        # RequestFactory não passa pelo middleware que o instala.
        pedido.user = AnonymousUser()
        return pedido

    def _html(self):
        from voluntario.views import LoginPCF
        return LoginPCF.as_view()(self._pedido()).rendered_content

    @override_settings(**CONFIG)
    def test_com_client_id_o_botao_aparece(self):
        html = self._html()
        self.assertIn('id-de-teste.apps.googleusercontent.com', html)
        self.assertIn('accounts.google.com/gsi/client', html)

    @override_settings(GOOGLE_LOGIN_CLIENT_ID='', GOOGLE_LOGIN_DOMINIO=DOMINIO)
    def test_sem_client_id_o_botao_nao_aparece(self):
        """Máquina sem a chave: o formulário de senha continua inteiro."""
        html = self._html()
        self.assertNotIn('accounts.google.com/gsi/client', html)
        self.assertIn('name="username"', html)

    @override_settings(**CONFIG)
    def test_o_dominio_vai_como_dica_para_o_seletor_de_conta(self):
        """`data-hd` faz o Google já filtrar a lista de contas. É conforto, não
        segurança: quem barra de verdade é a checagem no servidor."""
        self.assertIn(DOMINIO, self._html())

    @override_settings(**CONFIG)
    def test_a_tela_mostra_recado(self):
        """A tela NÃO renderizava `messages`. Toda recusa da entrada pelo
        Google seria escrita e nunca vista — o mesmo defeito que a tela do
        Bazar tinha: o voluntário aperta, nada aparece, e ele aperta de novo.
        """
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib import messages as django_messages
        from voluntario.views import LoginPCF

        pedido = self._pedido()
        pedido._messages = FallbackStorage(pedido)
        django_messages.error(pedido, 'RECADO DE TESTE PARA O VOLUNTARIO')

        html = LoginPCF.as_view()(pedido).rendered_content

        self.assertIn('RECADO DE TESTE PARA O VOLUNTARIO', html)
