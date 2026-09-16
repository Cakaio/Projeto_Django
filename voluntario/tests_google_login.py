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


def soltar_a_trava_de_email():
    """Deixa o banco de teste aceitar e-mail repetido.

    É o estado do banco REAL antes da migration 0020: a duplicata existe, e é
    justamente por isso que há código tratando dela. Sem isso, os testes da
    ambiguidade não teriam como montar o cenário que precisam provar.
    """
    from django.db import connection

    nome = 'voluntario_email_unico_quando_preenchido'
    with connection.cursor() as cursor:
        try:
            cursor.execute(f'DROP INDEX {nome}')
        except Exception:
            cursor.execute(
                f'ALTER TABLE voluntario_voluntario DROP CONSTRAINT {nome}')


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
        soltar_a_trava_de_email()   # banco anterior a migration 0020
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


class EmailUnicoTests(TestCase):
    """A trava de banco que impede a ambiguidade de nascer.

    `voluntario_para` já recusa login quando acha dois cadastros com o mesmo
    e-mail — mas aí é tarde: a pessoa descobre no sábado, tentando entrar. A
    constraint existe para a situação não chegar a existir.
    """

    def test_dois_cadastros_com_o_mesmo_email_sao_recusados_pelo_banco(self):
        from django.db import IntegrityError, transaction

        Voluntario.objects.create_user(username='a1', password='x',
                                       area='MARKETING', email='ana@pcf.org')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Voluntario.objects.create_user(username='a2', password='x',
                                               area='MARKETING',
                                               email='ana@pcf.org')

    def test_a_trava_ignora_maiuscula(self):
        """A busca do login é `email__iexact`. Uma trava sensível a caixa
        deixaria 'Ana@' e 'ana@' entrarem e o login continuaria ambíguo."""
        from django.db import IntegrityError, transaction

        Voluntario.objects.create_user(username='a1', password='x',
                                       area='MARKETING', email='ana@pcf.org')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Voluntario.objects.create_user(username='a2', password='x',
                                               area='MARKETING',
                                               email='ANA@PCF.ORG')

    def test_varios_sem_email_continuam_permitidos(self):
        """Voluntário antigo sem e-mail é o normal. Um único sobre '' proibiria
        o segundo cadastro sem e-mail — e aí ninguém cadastraria mais ninguém."""
        for nome in ('b1', 'b2', 'b3'):
            Voluntario.objects.create_user(username=nome, password='x',
                                           area='MARKETING', email='')

        self.assertEqual(Voluntario.objects.filter(email='').count(), 3)


class MigrationDoEmailUnicoTests(TestCase):
    """A conferência que roda ANTES de criar o índice.

    Um `IntegrityError` no meio do `migrate` só diz "deu ruim". Quem está no
    servidor precisa saber QUAIS cadastros brigaram, sem abrir o banco.
    """

    def _conferir(self):
        import importlib
        from django.apps import apps as apps_reais
        # O nome do módulo começa com dígito: só dá para importar assim.
        modulo = importlib.import_module(
            'voluntario.migrations.0020_email_unico_por_voluntario')
        return modulo.conferir_antes(apps_reais, None)

    def test_banco_limpo_passa(self):
        Voluntario.objects.create_user(username='a1', password='x',
                                       area='MARKETING', email='ana@pcf.org')
        Voluntario.objects.create_user(username='a2', password='x',
                                       area='MARKETING', email='')
        self.assertIsNone(self._conferir())

    def test_duplicata_e_denunciada_com_nome_e_id(self):
        """Sem os nomes, a mensagem manda procurar agulha em 300 cadastros."""
        # A constraint já existe no banco de teste, então a duplicata precisa
        # ser plantada por fora dela — é o estado que o servidor REAL pode ter
        # hoje, antes da migration rodar.
        soltar_a_trava_de_email()

        Voluntario.objects.create_user(username='ana.silva', password='x',
                                       area='MARKETING', email='ana@pcf.org')
        Voluntario.objects.create_user(username='ana.souza', password='x',
                                       area='MARKETING', email='ANA@pcf.org')

        with self.assertRaises(Exception) as caixa:
            self._conferir()

        recado = str(caixa.exception)
        self.assertIn('ana@pcf.org', recado)
        self.assertIn('ana.silva', recado)
        self.assertIn('ana.souza', recado)
        self.assertIn('Nada foi alterado no banco', recado)


class BotaoNoCelularTests(TestCase):
    """O botão do Google não pode alargar a tela de login."""

    def test_a_largura_fixa_cabe_no_celular(self):
        """`data-width` é pixel fixo dentro de um iframe que não encolhe.

        Conta do espaço útil num aparelho de 360px: 360 − 40 (respiro da
        `.lg-main`) − 56 (recheio do cartão) = 264px. Valor maior que isso põe
        rolagem horizontal na tela de entrada, no aparelho de todo mundo.
        """
        import re
        from pathlib import Path
        from django.conf import settings

        html = (Path(settings.BASE_DIR) / 'templates' / 'login.html'
                ).read_text(encoding='utf-8')
        larguras = [int(v) for v in re.findall(r'data-width="(\d+)"', html)]

        self.assertTrue(larguras, 'O botão do Google perdeu o data-width.')
        for largura in larguras:
            self.assertLessEqual(
                largura, 264,
                f'data-width={largura} não cabe em celular de 360px.')


class DominioVazioTests(TestCase):
    """A única forma de este recurso virar um buraco.

    Sem `GOOGLE_LOGIN_DOMINIO` não há com o que comparar o `hd`, e qualquer
    conta Google do planeta viraria voluntário ATIVO — por causa de uma linha
    em branco no `.env`, que não parece nada.
    """

    CONFIG_SEM_DOMINIO = dict(
        GOOGLE_LOGIN_CLIENT_ID='id-de-teste.apps.googleusercontent.com',
        GOOGLE_LOGIN_DOMINIO='')

    @override_settings(**CONFIG_SEM_DOMINIO)
    def test_sem_dominio_o_botao_nao_aparece(self):
        self.assertFalse(google_login.configurado())

    @override_settings(**CONFIG_SEM_DOMINIO)
    def test_sem_dominio_nem_um_gmail_comum_entra(self):
        """A recusa é repetida dentro de `verificar_credencial` de propósito:
        é a última linha antes de alguém entrar, e não pode depender de outra
        função ter sido chamada antes."""
        with patch('voluntario.google_login.id_token.verify_oauth2_token',
                   return_value=carga(hd=None, email='qualquer@gmail.com')):
            with self.assertRaises(LoginGoogleInvalido):
                google_login.verificar_credencial('token')

    @override_settings(**CONFIG_SEM_DOMINIO)
    def test_o_deploy_avisa_por_que_o_botao_sumiu(self):
        """Falhar fechado em silêncio faz quem configurou procurar erro no
        Google Cloud Console. O aviso diz que é a linha do `.env`."""
        from TESTE.checks import entrada_pelo_google_tem_dominio

        avisos = entrada_pelo_google_tem_dominio(app_configs=None)

        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0].id, 'pcf.W002')
        self.assertIn('GOOGLE_LOGIN_DOMINIO', avisos[0].hint)

    @override_settings(**CONFIG)
    def test_configuracao_completa_nao_avisa(self):
        from TESTE.checks import entrada_pelo_google_tem_dominio
        self.assertEqual(entrada_pelo_google_tem_dominio(app_configs=None), [])

    @override_settings(GOOGLE_LOGIN_CLIENT_ID='', GOOGLE_LOGIN_DOMINIO='')
    def test_servidor_sem_o_recurso_nao_vira_barulho(self):
        """Máquina de desenvolvimento não tem nada disso, e não precisa ouvir
        sobre isso em todo `manage.py` do dia."""
        from TESTE.checks import entrada_pelo_google_tem_dominio
        self.assertEqual(entrada_pelo_google_tem_dominio(app_configs=None), [])


@override_settings(**CONFIG)
class SemABibliotecaDoGoogleTests(TestCase):
    """A tela de login NAO PODE cair por causa deste recurso.

    Em 09/2026 ela caiu: `google_login.py` importava o `google` no topo do
    módulo, e o venv do servidor não tinha a biblioteca. Resultado: 500 em
    `/login/` — a única página que precisa abrir mesmo quando tudo o mais está
    quebrado, porque sem ela ninguém entra para consertar nada.

    `acervo/drive.py` já importava dentro da função. A regra do CLAUDE.md sobre
    `notificacoes.services` é a mesma, escrita para outro módulo.
    """

    def test_a_tela_de_login_abre_sem_a_biblioteca(self):
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory
        from voluntario.views import LoginPCF

        pedido = RequestFactory().get('/login/')
        pedido.user = AnonymousUser()
        pedido.session = self.client.session

        with patch.object(google_login, 'id_token', None):
            html = LoginPCF.as_view()(pedido).rendered_content

        # A tela abre, e abre INTEIRA: o caminho de usuário e senha é o que
        # continua funcionando quando o Google não está disponível.
        self.assertIn('name="username"', html)
        self.assertIn('name="password"', html)

    def test_sem_a_biblioteca_o_botao_nao_aparece(self):
        """Pior que não ter o botão é ter um botão que estoura ao ser tocado."""
        with patch.object(google_login, 'id_token', None):
            self.assertFalse(google_login.configurado())

    def test_sem_a_biblioteca_ninguem_entra(self):
        with patch.object(google_login, 'id_token', None):
            with self.assertRaises(LoginGoogleInvalido):
                google_login.verificar_credencial('token')

    def test_o_deploy_avisa_que_falta_instalar(self):
        """Sem isto, o botão some e quem configurou vai procurar erro no
        Google Cloud Console — de novo."""
        from TESTE.checks import biblioteca_do_google_instalada

        with patch.object(google_login, 'id_token', None):
            avisos = biblioteca_do_google_instalada(app_configs=None)

        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0].id, 'pcf.W003')
        self.assertIn('requirements.txt', avisos[0].hint)

    def test_com_a_biblioteca_nao_vira_barulho(self):
        from TESTE.checks import biblioteca_do_google_instalada
        self.assertEqual(biblioteca_do_google_instalada(app_configs=None), [])
