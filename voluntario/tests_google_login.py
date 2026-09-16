"""Entrar com a conta Google da organização.

O que estes testes protegem não é conveniência, é a porta de entrada do
sistema. Um erro aqui deixa alguém de fora do projeto entrar como voluntário —
e o sistema tem ficha de criança dentro.
"""
import datetime
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from voluntario import google_login
from voluntario.google_login import LoginGoogleInvalido

Voluntario = get_user_model()

DOMINIO = 'projetocriancafeliz.org'
CONFIG = dict(GOOGLE_LOGIN_CLIENT_ID='id-de-teste.apps.googleusercontent.com',
              GOOGLE_LOGIN_CLIENT_SECRET='segredo-de-teste',
              GOOGLE_LOGIN_DOMINIO=DOMINIO)

NONCE = 'nonce-de-teste'


def carga(**extras):
    """O que o Google devolve num token válido da organização."""
    dados = {
        'email': 'ana@projetocriancafeliz.org',
        'email_verified': True,
        'hd': DOMINIO,
        'nonce': NONCE,
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


def pedido_com_sessao(fabrica_metodo, *args, **kwargs):
    """Um request com sessão e caixa de recados, como o middleware faria."""
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.backends.db import SessionStore

    pedido = fabrica_metodo(*args, **kwargs)
    pedido.user = AnonymousUser()
    pedido.session = SessionStore()
    pedido._messages = FallbackStorage(pedido)
    return pedido


@override_settings(**CONFIG)
class VerificacaoDoTokenTests(TestCase):
    """Nada do que chega de fora é aceito: quem valida é o Google."""

    def _verificar(self, devolvido, nonce=NONCE):
        with patch('voluntario.google_login.id_token.verify_oauth2_token',
                   return_value=devolvido):
            return google_login.verificar_credencial('token-qualquer',
                                                     nonce_esperado=nonce)

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

    def test_nonce_diferente_e_recusado(self):
        """`verify_oauth2_token` NÃO confere o nonce — isso é por nossa conta.

        Sem esta checagem, um token de identidade válido para este mesmo
        aplicativo, obtido em outro lugar, entraria aqui.
        """
        with self.assertRaises(LoginGoogleInvalido):
            self._verificar(carga(nonce='de-outro-pedido'))

    def test_token_sem_nonce_e_recusado(self):
        with self.assertRaises(LoginGoogleInvalido):
            self._verificar(carga(nonce=None))

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
class IdaAoGoogleTests(TestCase):
    """A ida: o que é sorteado agora é o que protege a volta."""

    def _endereco(self):
        from django.test import RequestFactory

        pedido = pedido_com_sessao(RequestFactory().get, '/login/google/ir/')
        endereco = google_login.endereco_de_ida(
            pedido, 'https://pcf.pythonanywhere.com/login/google/')
        return pedido, endereco, parse_qs(urlparse(endereco).query)

    def test_pede_codigo_e_nao_token_direto(self):
        """`SESSION_COOKIE_SAMESITE = 'Lax'` não manda o cookie de sessão num
        POST vindo de outro site. O modo `form_post` chegaria SEM SESSÃO — sem
        `state` nem `nonce` para conferir."""
        _, _, parametros = self._endereco()
        self.assertEqual(parametros['response_type'], ['code'])
        self.assertNotIn('response_mode', parametros)

    def test_state_e_nonce_ficam_na_sessao(self):
        pedido, _, parametros = self._endereco()
        self.assertEqual(pedido.session[google_login.CHAVE_STATE],
                         parametros['state'][0])
        self.assertEqual(pedido.session[google_login.CHAVE_NONCE],
                         parametros['nonce'][0])

    def test_cada_ida_sorteia_valores_novos(self):
        _, _, primeira = self._endereco()
        _, _, segunda = self._endereco()
        self.assertNotEqual(primeira['state'], segunda['state'])
        self.assertNotEqual(primeira['nonce'], segunda['nonce'])

    def test_pede_para_escolher_a_conta(self):
        """Sem `prompt=select_account`, quem já tem sessão Google entra direto
        com ela e não consegue trocar — problema real no computador do
        projeto, que é compartilhado."""
        _, _, parametros = self._endereco()
        self.assertEqual(parametros['prompt'], ['select_account'])

    def test_leva_o_dominio_como_dica(self):
        _, _, parametros = self._endereco()
        self.assertEqual(parametros['hd'], [DOMINIO])

    def test_o_segredo_nao_vai_no_endereco(self):
        """O segredo é usado servidor a servidor. Se vazasse para a URL, ele
        estaria no histórico do navegador e no log de qualquer proxy."""
        _, endereco, _ = self._endereco()
        self.assertNotIn('segredo-de-teste', endereco)


@override_settings(**CONFIG)
class VoltaDoGoogleTests(TestCase):
    """A volta: aqui é onde alguém tentaria entrar sem ter começado."""

    def setUp(self):
        from django.test import RequestFactory
        self.fabrica = RequestFactory()

    def _voltar(self, parametros, state_na_sessao='abc', nonce_na_sessao=NONCE,
                devolvido=None):
        from voluntario.views import entrar_com_google

        pedido = pedido_com_sessao(self.fabrica.get, '/login/google/',
                                   parametros)
        if state_na_sessao is not None:
            pedido.session[google_login.CHAVE_STATE] = state_na_sessao
        if nonce_na_sessao is not None:
            pedido.session[google_login.CHAVE_NONCE] = nonce_na_sessao

        with patch('voluntario.google_login.trocar_codigo_por_token',
                   return_value='token'), \
             patch('voluntario.google_login.id_token.verify_oauth2_token',
                   return_value=devolvido or carga()):
            return pedido, entrar_com_google(pedido)

    def test_conta_da_organizacao_entra(self):
        Voluntario.objects.create_user(
            username='ana', password='x', area='MARKETING',
            email='ana@projetocriancafeliz.org')

        pedido, resposta = self._voltar({'code': 'c', 'state': 'abc'})

        self.assertEqual(resposta.status_code, 302)
        self.assertIn('_auth_user_id', pedido.session)

    def test_state_errado_nao_entra(self):
        """Sem isto, alguém poderia mandar ao voluntário um link de volta já
        pronto e fazê-lo entrar na conta Google do atacante sem perceber."""
        pedido, resposta = self._voltar({'code': 'c', 'state': 'outro'})

        self.assertIn('/login/', resposta.url)
        self.assertNotIn('_auth_user_id', pedido.session)

    def test_volta_sem_ter_ido_nao_entra(self):
        """Abrir o endereço de volta direto, sem `state` na sessão."""
        pedido, resposta = self._voltar({'code': 'c', 'state': 'abc'},
                                        state_na_sessao=None)

        self.assertIn('/login/', resposta.url)
        self.assertNotIn('_auth_user_id', pedido.session)

    def test_a_mesma_volta_nao_vale_duas_vezes(self):
        """O `state` é consumido: reenviar o mesmo endereço não entra de novo."""
        from voluntario.views import entrar_com_google

        Voluntario.objects.create_user(
            username='ana', password='x', area='MARKETING',
            email='ana@projetocriancafeliz.org')

        pedido, primeira = self._voltar({'code': 'c', 'state': 'abc'})
        self.assertIn('_auth_user_id', pedido.session)

        # Mesmo request, mesma sessão, de novo.
        pedido.session.pop('_auth_user_id', None)
        with patch('voluntario.google_login.trocar_codigo_por_token',
                   return_value='token'), \
             patch('voluntario.google_login.id_token.verify_oauth2_token',
                   return_value=carga()):
            entrar_com_google(pedido)

        self.assertNotIn('_auth_user_id', pedido.session)

    def test_conta_de_fora_nao_entra(self):
        pedido, resposta = self._voltar(
            {'code': 'c', 'state': 'abc'},
            devolvido=carga(hd='outraong.org', email='x@outraong.org'))

        self.assertIn('/login/', resposta.url)
        self.assertNotIn('_auth_user_id', pedido.session)

    def test_desistir_no_google_nao_e_erro(self):
        """Fechar a tela do Google é escolha, não falha. Merece recado calmo."""
        from django.contrib.messages import get_messages
        from voluntario.views import entrar_com_google

        pedido = pedido_com_sessao(self.fabrica.get, '/login/google/',
                                   {'error': 'access_denied'})
        resposta = entrar_com_google(pedido)

        recados = list(get_messages(pedido))
        self.assertIn('/login/', resposta.url)
        self.assertNotIn('error', ' '.join(m.level_tag for m in recados))

    def test_volta_sem_codigo_nao_estoura(self):
        pedido, resposta = self._voltar({'state': 'abc'})
        self.assertEqual(resposta.status_code, 302)
        self.assertNotIn('_auth_user_id', pedido.session)

    def test_primeira_entrada_avisa_para_procurar_a_gt(self):
        from django.contrib.messages import get_messages

        pedido, _ = self._voltar({'code': 'c', 'state': 'abc'})

        recados = ' '.join(str(m) for m in get_messages(pedido))
        self.assertIn('Gestão de Talentos', recados)
        self.assertTrue(Voluntario.objects.filter(
            email='ana@projetocriancafeliz.org').exists())


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
    def test_configurado_com_tudo_no_lugar(self):
        self.assertTrue(google_login.configurado())

    @override_settings(**{**CONFIG, 'GOOGLE_LOGIN_CLIENT_ID': ''})
    def test_sem_client_id_nao_esta_configurado(self):
        """Máquina sem a chave não pode quebrar: o botão só não aparece."""
        self.assertFalse(google_login.configurado())

    @override_settings(**{**CONFIG, 'GOOGLE_LOGIN_CLIENT_SECRET': ''})
    def test_sem_segredo_nao_esta_configurado(self):
        """Sem o segredo a troca do código falha DEPOIS de o voluntário ir ao
        Google e voltar. Botão que leva a um beco é pior que botão nenhum."""
        self.assertFalse(google_login.configurado())


class TelaDeLoginTests(TestCase):
    """O botão, e o recado que o botão precisa poder mostrar."""

    def _pedido(self):
        from django.test import RequestFactory
        return pedido_com_sessao(RequestFactory().get, '/login/')

    def _html(self, pedido=None):
        from voluntario.views import LoginPCF
        return LoginPCF.as_view()(pedido or self._pedido()).rendered_content

    @override_settings(**CONFIG)
    def test_o_botao_aparece_e_e_nosso(self):
        html = self._html()
        self.assertIn('Entrar com Google', html)
        self.assertIn('/login/google/ir/', html)

    @override_settings(**CONFIG)
    def test_o_widget_do_google_nao_volta(self):
        """O `gsi/client` desenha o botão num iframe e depende de cookie de
        terceiro e FedCM. Em produção travava em `/gsi/transform` sem erro
        nenhum, e saía escrito em inglês apesar do `data-locale`."""
        html = self._html()
        self.assertNotIn('gsi/client', html)
        self.assertNotIn('g_id_onload', html)

    @override_settings(**CONFIG)
    def test_o_client_id_nao_vai_para_a_pagina(self):
        """Com o redirecionamento quem monta o endereço é o servidor. O que
        não precisa sair daqui, não sai."""
        self.assertNotIn(CONFIG['GOOGLE_LOGIN_CLIENT_ID'], self._html())

    @override_settings(**{**CONFIG, 'GOOGLE_LOGIN_CLIENT_ID': ''})
    def test_sem_client_id_o_botao_nao_aparece(self):
        """Máquina sem a chave: o formulário de senha continua inteiro."""
        html = self._html()
        self.assertNotIn('Entrar com Google', html)
        self.assertIn('name="username"', html)

    @override_settings(**CONFIG)
    def test_a_tela_diz_de_quem_e_a_entrada(self):
        self.assertIn(DOMINIO, self._html())

    @override_settings(**CONFIG)
    def test_a_tela_mostra_recado(self):
        """A tela NÃO renderizava `messages`. Toda recusa da entrada pelo
        Google seria escrita e nunca vista — o mesmo defeito que a tela do
        Bazar tinha: o voluntário aperta, nada aparece, e ele aperta de novo.
        """
        from django.contrib import messages as django_messages

        pedido = self._pedido()
        django_messages.error(pedido, 'RECADO DE TESTE PARA O VOLUNTARIO')

        self.assertIn('RECADO DE TESTE PARA O VOLUNTARIO', self._html(pedido))


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


class DominioVazioTests(TestCase):
    """A única forma de este recurso virar um buraco.

    Sem `GOOGLE_LOGIN_DOMINIO` não há com o que comparar o `hd`, e qualquer
    conta Google do planeta viraria voluntário ATIVO — por causa de uma linha
    em branco no `.env`, que não parece nada.
    """

    SEM_DOMINIO = {**CONFIG, 'GOOGLE_LOGIN_DOMINIO': ''}

    @override_settings(**SEM_DOMINIO)
    def test_sem_dominio_o_botao_nao_aparece(self):
        self.assertFalse(google_login.configurado())

    @override_settings(**SEM_DOMINIO)
    def test_sem_dominio_nem_um_gmail_comum_entra(self):
        """A recusa é repetida dentro de `verificar_credencial` de propósito:
        é a última linha antes de alguém entrar, e não pode depender de outra
        função ter sido chamada antes."""
        with patch('voluntario.google_login.id_token.verify_oauth2_token',
                   return_value=carga(hd=None, email='qualquer@gmail.com')):
            with self.assertRaises(LoginGoogleInvalido):
                google_login.verificar_credencial('token', nonce_esperado=NONCE)

    @override_settings(**SEM_DOMINIO)
    def test_o_deploy_avisa_por_que_o_botao_sumiu(self):
        """Falhar fechado em silêncio faz quem configurou procurar erro no
        Google Cloud Console. O aviso diz que é a linha do `.env`."""
        from TESTE.checks import entrada_pelo_google_tem_dominio

        avisos = entrada_pelo_google_tem_dominio(app_configs=None)

        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0].id, 'pcf.W002')
        self.assertIn('GOOGLE_LOGIN_DOMINIO', avisos[0].msg)

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
        from django.test import RequestFactory
        from voluntario.views import LoginPCF

        pedido = pedido_com_sessao(RequestFactory().get, '/login/')

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


class BotaoNoCelularTests(TestCase):
    """O botão do Google não pode alargar a tela de login."""

    def test_nenhuma_largura_fixa_no_botao(self):
        """O widget do Google exigia `data-width` em PIXEL, e 320 não cabia em
        celular nenhum (num aparelho de 360px sobram 264px no cartão). Com
        botão nosso o problema deixa de existir: ele acompanha a largura, igual
        ao botão "Entrar". Este teste existe para não voltar."""
        import re
        from pathlib import Path
        from django.conf import settings

        html = (Path(settings.BASE_DIR) / 'templates' / 'login.html'
                ).read_text(encoding='utf-8')

        self.assertEqual(re.findall(r'data-width="(\d+)"', html), [])
        self.assertIn('pcf-btn-block', html)


class SegredoAusenteTests(TestCase):
    """Client ID posto e segredo esquecido é a metade de configuração mais
    provável — e a que falharia só na VOLTA do Google, longe da causa."""

    @override_settings(**{**CONFIG, 'GOOGLE_LOGIN_CLIENT_SECRET': ''})
    def test_o_deploy_diz_que_falta_o_segredo(self):
        from TESTE.checks import entrada_pelo_google_tem_dominio

        avisos = entrada_pelo_google_tem_dominio(app_configs=None)

        self.assertEqual(len(avisos), 1)
        self.assertIn('GOOGLE_LOGIN_CLIENT_SECRET', avisos[0].msg)
        self.assertNotIn('GOOGLE_LOGIN_DOMINIO', avisos[0].msg)

    @override_settings(**{**CONFIG, 'GOOGLE_LOGIN_CLIENT_SECRET': '',
                          'GOOGLE_LOGIN_DOMINIO': ''})
    def test_faltando_os_dois_o_aviso_cita_os_dois(self):
        """Avisar de um por vez faria a pessoa recarregar o site duas vezes."""
        from TESTE.checks import entrada_pelo_google_tem_dominio

        avisos = entrada_pelo_google_tem_dominio(app_configs=None)

        self.assertEqual(len(avisos), 1)
        self.assertIn('GOOGLE_LOGIN_CLIENT_SECRET', avisos[0].msg)
        self.assertIn('GOOGLE_LOGIN_DOMINIO', avisos[0].msg)
