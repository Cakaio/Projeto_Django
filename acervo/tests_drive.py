"""Testes da sincronização com o Google Drive.

Nenhum destes testes toca a rede. `acervo/sincronizacao.py` recebe o cliente
como argumento justamente para isso: aqui entra um dublê que devolve pastas e
arquivos de mentira, e a lógica inteira — decidir o ano, recusar formato,
agrupar em coleção, não retrazer o que já entrou — é exercitada de verdade.

O que NÃO está coberto, e é honesto registrar: autenticação por conta de
serviço, exportação de Google Docs para PDF pela API real, paginação com muitos
arquivos e pasta em Drive compartilhado. Essas partes só se provam rodando
contra o Drive de verdade.
"""
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase, override_settings

from acervo import drive
from acervo.models import Colecao, Documento, SincronizacaoDrive
from acervo.sincronizacao import Placar, sincronizar

Voluntario = get_user_model()

PASTA_RAIZ = 'raiz-id'


class DriveFalso:
    """Dublê do serviço do Drive.

    Guarda as pastas e os arquivos numa árvore em memória e responde às três
    perguntas que `acervo/drive.py` faz: quais são as subpastas, quais são os
    arquivos abaixo de uma pasta, e quais são os bytes de um arquivo.
    """

    def __init__(self):
        self.pastas = {}      # pasta_id -> [subpasta, ...]
        self.arquivos = {}    # pasta_id -> [arquivo, ...]
        self.conteudo = {}    # arquivo_id -> bytes
        self.baixados = []    # ordem dos downloads, para asserção
        self.recusar = set()  # ids que devem falhar no download

    def pasta(self, pasta_id, nome, dentro_de=PASTA_RAIZ):
        self.pastas.setdefault(dentro_de, []).append(
            {'id': pasta_id, 'name': nome, 'mimeType': drive.TIPO_PASTA})
        return pasta_id

    def arquivo(self, arquivo_id, nome, dentro_de, tamanho=1000,
                tipo='application/pdf', conteudo=b'conteudo'):
        item = {'id': arquivo_id, 'name': nome, 'mimeType': tipo}
        if tipo not in drive.EXPORTAVEIS:
            # Arquivo nativo do Google não tem `size` na API — a ausência aqui
            # é o que faz o teste exercitar esse caminho.
            item['size'] = str(tamanho)
        self.arquivos.setdefault(dentro_de, []).append(item)
        self.conteudo[arquivo_id] = conteudo
        return item


def _subpastas_falsas(servico, pasta_id):
    return list(servico.pastas.get(pasta_id, []))


def _arvore_falsa(servico, pasta_id, nome_da_pasta=''):
    encontrados = []
    fila = [(pasta_id, [nome_da_pasta] if nome_da_pasta else [])]
    while fila:
        atual, caminho = fila.pop()
        for sub in servico.pastas.get(atual, []):
            fila.append((sub['id'], [sub['name']] + caminho))
        for arq in servico.arquivos.get(atual, []):
            encontrados.append({**arq, 'pastas': caminho})
    return encontrados


def _baixar_falso(servico, arquivo):
    if arquivo['id'] in servico.recusar:
        raise drive.HttpError('sem permissão')
    servico.baixados.append(arquivo['id'])
    return servico.conteudo[arquivo['id']]


class BaseDrive(TestCase):
    def setUp(self):
        pasta = tempfile.mkdtemp(prefix='acervo-drive-')
        self.addCleanup(shutil.rmtree, pasta, ignore_errors=True)
        self._media = override_settings(MEDIA_ROOT=pasta)
        self._media.enable()
        self.addCleanup(self._media.disable)

        self.drive = DriveFalso()

        for alvo, substituto in (
            ('acervo.drive.subpastas', _subpastas_falsas),
            ('acervo.drive.arquivos_da_arvore', _arvore_falsa),
            ('acervo.drive.baixar', _baixar_falso),
        ):
            remendo = patch(alvo, substituto)
            remendo.start()
            self.addCleanup(remendo.stop)

    def sincronizar(self, **extras):
        return sincronizar(self.drive, PASTA_RAIZ, Placar(), **extras)


class EstruturaTest(BaseDrive):

    def test_cada_subpasta_do_drive_vira_uma_colecao(self):
        self.drive.pasta('p1', 'Postulações 2023')
        self.drive.arquivo('a1', 'joao.pdf', 'p1')
        self.drive.pasta('p2', 'Atas 2024')
        self.drive.arquivo('a2', 'ata.pdf', 'p2')

        self.sincronizar()

        self.assertTrue(Colecao.objects.filter(nome='Postulações 2023').exists())
        self.assertTrue(Colecao.objects.filter(nome='Atas 2024').exists())

    def test_arquivo_em_subpasta_profunda_entra_na_colecao_do_topo(self):
        self.drive.pasta('p1', 'Postulações 2023')
        self.drive.pasta('p1a', 'Eleitos', dentro_de='p1')
        self.drive.arquivo('a1', 'joao.pdf', 'p1a')

        self.sincronizar()

        colecao = Colecao.objects.get(nome='Postulações 2023')
        self.assertEqual(colecao.documentos.count(), 1)

    def test_pasta_sem_nada_aproveitavel_nao_cria_colecao(self):
        self.drive.pasta('p1', 'Vídeos')
        self.drive.arquivo('a1', 'clipe.mp4', 'p1', tipo='video/mp4')

        self.sincronizar()

        self.assertFalse(Colecao.objects.filter(nome='Vídeos').exists())

    def test_colecao_existente_e_reaproveitada(self):
        Colecao.objects.create(nome='Atas 2024', descricao='Já existia')
        self.drive.pasta('p1', 'Atas 2024')
        self.drive.arquivo('a1', 'ata.pdf', 'p1')

        self.sincronizar()

        self.assertEqual(Colecao.objects.filter(nome='Atas 2024').count(), 1)
        self.assertEqual(Colecao.objects.get(nome='Atas 2024').descricao, 'Já existia')


class IncrementalTest(BaseDrive):
    """O ponto do pedido: não retrazer o que já entrou."""

    def setUp(self):
        super().setUp()
        self.drive.pasta('p1', 'Atas 2024')
        self.drive.arquivo('a1', 'ata.pdf', 'p1')

    def test_a_segunda_rodada_nao_traz_nada(self):
        primeira = self.sincronizar()
        self.assertEqual(primeira.trazidos, 1)

        segunda = self.sincronizar()
        self.assertEqual(segunda.trazidos, 0)
        self.assertEqual(Documento.objects.count(), 1)

    def test_a_segunda_rodada_nem_baixa_de_novo(self):
        """Não basta não duplicar: não pode gastar banda com o que já entrou."""
        self.sincronizar()
        self.drive.baixados.clear()

        self.sincronizar()
        self.assertEqual(self.drive.baixados, [])

    def test_arquivo_renomeado_no_drive_nao_volta(self):
        """O ID do Drive não muda quando o arquivo é renomeado.

        Comparar por título faria um documento duplicado aparecer toda vez que
        alguém arrumasse o nome de um arquivo lá.
        """
        self.sincronizar()
        self.drive.arquivos['p1'][0]['name'] = 'ata-da-reuniao-geral.pdf'

        self.sincronizar()
        self.assertEqual(Documento.objects.count(), 1)

    def test_arquivo_novo_no_drive_entra_na_rodada_seguinte(self):
        self.sincronizar()
        self.drive.arquivo('a2', 'ata-nova-2024.pdf', 'p1')

        placar = self.sincronizar()
        self.assertEqual(placar.trazidos, 1)
        self.assertEqual(Documento.objects.count(), 2)

    def test_o_id_do_drive_fica_gravado_no_documento(self):
        self.sincronizar()
        self.assertEqual(Documento.objects.get().origem_drive_id, 'a1')


class AnoTest(BaseDrive):

    def test_ano_sai_do_nome_do_arquivo(self):
        self.drive.pasta('p1', 'Atas')
        self.drive.arquivo('a1', 'reuniao-2021.pdf', 'p1')
        self.sincronizar()
        self.assertEqual(Documento.objects.get().ano, 2021)

    def test_ano_sai_da_pasta_do_meio(self):
        """Uma varredura plana perderia isto: o ano está na pasta intermediária."""
        self.drive.pasta('p1', 'Postulações')
        self.drive.pasta('p1a', '2019', dentro_de='p1')
        self.drive.arquivo('a1', 'joao.pdf', 'p1a')

        self.sincronizar()
        self.assertEqual(Documento.objects.get().ano, 2019)

    def test_ano_do_arquivo_vence_o_da_pasta(self):
        self.drive.pasta('p1', 'Postulações 2019')
        self.drive.arquivo('a1', 'ata-2023.pdf', 'p1')
        self.sincronizar()
        self.assertEqual(Documento.objects.get().ano, 2023)

    def test_sem_ano_o_arquivo_e_pulado_e_o_motivo_fica_registrado(self):
        self.drive.pasta('p1', 'Atas')
        self.drive.arquivo('a1', 'reuniao.pdf', 'p1')

        placar = self.sincronizar()
        self.assertEqual(Documento.objects.count(), 0)
        self.assertIn('sem ano', placar.texto())


class FiltrosTest(BaseDrive):

    def test_formato_nao_aceito_e_pulado(self):
        self.drive.pasta('p1', 'Atas 2024')
        self.drive.arquivo('a1', 'planilha.xlsx', 'p1',
                           tipo='application/vnd.ms-excel')

        placar = self.sincronizar()
        self.assertEqual(Documento.objects.count(), 0)
        self.assertIn('.xlsx', placar.texto())

    def test_arquivo_grande_demais_e_pulado_sem_baixar(self):
        """Recusar depois de baixar 200 MB seria desperdício puro."""
        self.drive.pasta('p1', 'Atas 2024')
        self.drive.arquivo('a1', 'enorme.pdf', 'p1', tamanho=100 * 1024 * 1024)

        self.sincronizar()
        self.assertEqual(self.drive.baixados, [])
        self.assertEqual(Documento.objects.count(), 0)

    def test_google_doc_e_exportado_como_pdf(self):
        """Arquivo nativo do Google não tem bytes nem `size` — só exportação."""
        self.drive.pasta('p1', 'Atas 2024')
        self.drive.arquivo('a1', 'Ata da reunião', 'p1',
                           tipo='application/vnd.google-apps.document')

        self.sincronizar()

        documento = Documento.objects.get()
        self.assertTrue(documento.arquivo.name.endswith('.pdf'))

    def test_um_arquivo_recusado_pelo_drive_nao_derruba_o_resto(self):
        self.drive.pasta('p1', 'Atas 2024')
        self.drive.arquivo('a1', 'sem-permissao.pdf', 'p1')
        self.drive.arquivo('a2', 'ok.pdf', 'p1')
        self.drive.recusar.add('a1')

        placar = self.sincronizar()

        self.assertEqual(Documento.objects.count(), 1)
        self.assertEqual(Documento.objects.get().origem_drive_id, 'a2')
        self.assertIn('recusou', placar.texto())


class DryRunTest(BaseDrive):

    def test_dry_run_conta_sem_baixar_nem_gravar(self):
        self.drive.pasta('p1', 'Atas 2024')
        self.drive.arquivo('a1', 'ata.pdf', 'p1')

        placar = self.sincronizar(dry_run=True)

        self.assertEqual(placar.trazidos, 1)
        self.assertEqual(Documento.objects.count(), 0)
        self.assertEqual(self.drive.baixados, [])


class ConteudoTest(BaseDrive):

    def test_o_arquivo_vai_para_a_pasta_protegida_por_login(self):
        self.drive.pasta('p1', 'Atas 2024')
        self.drive.arquivo('a1', 'ata.pdf', 'p1', conteudo=b'PDF da ata')

        self.sincronizar()

        documento = Documento.objects.get()
        self.assertTrue(documento.arquivo.name.startswith('acervo/'))
        self.assertEqual(documento.arquivo.read(), b'PDF da ata')

    def test_o_documento_diz_de_quem_e(self):
        """Documento.clean() exige atribuição; a sincronização usa o projeto."""
        self.drive.pasta('p1', 'Atas 2024')
        self.drive.arquivo('a1', 'ata.pdf', 'p1')

        self.sincronizar()
        self.assertTrue(Documento.objects.get().de_quem.strip())


@override_settings(ACERVO_DRIVE_CREDENCIAIS='', ACERVO_DRIVE_PASTA_ID='')
class BotaoDesligadoTest(TestCase):
    """Sem configuração, o botão não aparece — mas a Tríade entende por quê."""

    def setUp(self):
        self.factory = RequestFactory()
        self.triade = Voluntario.objects.create_user(
            username='triade', password='senha-de-teste-123', area='TRIADE')
        self.comum = Voluntario.objects.create_user(
            username='comum', password='senha-de-teste-123', area='AZUL')

    def _pedido(self, usuario, metodo='get'):
        pedido = getattr(self.factory, metodo)('/acervo/')
        pedido.user = usuario
        pedido.session = {}
        pedido._messages = FallbackStorage(pedido)
        return pedido

    def test_sem_credencial_o_botao_nao_aparece_na_tela(self):
        from acervo.views import lista

        resposta = lista(self._pedido(self.triade))
        self.assertNotIn('Trazer do Drive', resposta.content.decode())

    @patch('acervo.drive.build', object())   # finge a lib instalada
    def test_a_triade_ve_que_falta_a_pasta(self):
        from acervo.views import _aviso_do_drive

        aviso = _aviso_do_drive(pode_mexer_=True, ligado=False)
        self.assertIn('ACERVO_DRIVE_PASTA_ID', aviso)

    @patch('acervo.drive.build', object())
    @override_settings(ACERVO_DRIVE_PASTA_ID='raiz', ACERVO_DRIVE_CREDENCIAIS='')
    def test_com_a_pasta_definida_o_aviso_cobra_a_credencial(self):
        """E cita os DOIS caminhos: conta de serviço ou OAuth.

        Quem não pode compartilhar a pasta precisa saber que existe a segunda
        saída — senão trava achando que só a conta de serviço serve.
        """
        from acervo.views import _aviso_do_drive

        aviso = _aviso_do_drive(pode_mexer_=True, ligado=False)
        self.assertIn('ACERVO_DRIVE_CREDENCIAIS', aviso)
        self.assertIn('autorizar_acervo_drive', aviso)

    def test_sem_a_biblioteca_o_aviso_manda_instalar(self):
        """A biblioteca do Google não vem instalada — o aviso tem que dizer isso.

        É a primeira coisa que falta num servidor recém-atualizado, e sem esta
        frase a Tríade veria só "desligado" sem saber o que fazer.
        """
        from acervo.views import _aviso_do_drive

        with patch('acervo.drive.build', None):
            aviso = _aviso_do_drive(pode_mexer_=True, ligado=False)
        self.assertIn('pip install', aviso)

    def test_voluntario_comum_nao_ve_aviso_nenhum(self):
        """O estado da integração é assunto de quem administra, não da equipe."""
        from acervo.views import _aviso_do_drive

        self.assertEqual(_aviso_do_drive(pode_mexer_=False, ligado=False), '')

    def test_post_sem_configuracao_avisa_e_nao_dispara(self):
        from acervo.views import sincronizar_drive

        with patch('acervo.sincronizacao.rodar') as rodou:
            sincronizar_drive(self._pedido(self.triade, 'post'))
        rodou.assert_not_called()

    def test_voluntario_comum_nao_pode_disparar(self):
        from acervo.views import sincronizar_drive

        with self.assertRaises(PermissionDenied):
            sincronizar_drive(self._pedido(self.comum, 'post'))


@override_settings(ACERVO_DRIVE_CREDENCIAIS='/tmp/fake.json',
                   ACERVO_DRIVE_PASTA_ID='raiz-id')
class BotaoLigadoTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.triade = Voluntario.objects.create_user(
            username='triade', password='senha-de-teste-123', area='TRIADE')

    def _pedido(self, metodo='post'):
        pedido = getattr(self.factory, metodo)('/acervo/sincronizar/')
        pedido.user = self.triade
        pedido.session = {}
        pedido._messages = FallbackStorage(pedido)
        return pedido

    @patch('acervo.drive.build', object())   # finge a lib instalada
    def test_o_botao_dispara_em_thread(self):
        from acervo.views import sincronizar_drive

        with patch('threading.Thread') as thread:
            sincronizar_drive(self._pedido())
        thread.assert_called_once()
        # daemon=True: a thread não pode segurar o desligamento do worker.
        self.assertTrue(thread.call_args.kwargs['daemon'])

    @patch('acervo.drive.build', object())
    def test_get_nao_dispara_nada(self):
        """Sincronizar é ação, não leitura — link não pode disparar sem querer."""
        from acervo.views import sincronizar_drive

        with patch('threading.Thread') as thread:
            sincronizar_drive(self._pedido('get'))
        thread.assert_not_called()

    @patch('acervo.drive.build', object())
    def test_nao_dispara_duas_rodadas_ao_mesmo_tempo(self):
        from acervo.views import sincronizar_drive

        SincronizacaoDrive.objects.create(status=SincronizacaoDrive.RODANDO)

        with patch('threading.Thread') as thread:
            sincronizar_drive(self._pedido())
        thread.assert_not_called()

    @patch('acervo.drive.build', object())
    def test_registro_antigo_travado_nao_bloqueia_para_sempre(self):
        """Se o servidor reinicia no meio, a thread morre sem fechar o registro.

        Sem uma janela de validade, esse registro órfão travaria o botão para
        sempre e ninguém saberia por quê.
        """
        from datetime import timedelta

        from django.utils import timezone

        from acervo.views import sincronizar_drive

        antigo = SincronizacaoDrive.objects.create(status=SincronizacaoDrive.RODANDO)
        SincronizacaoDrive.objects.filter(pk=antigo.pk).update(
            comecou_em=timezone.now() - timedelta(hours=5))

        with patch('threading.Thread') as thread:
            sincronizar_drive(self._pedido())
        thread.assert_called_once()


class ModoDeAutenticacaoTest(TestCase):
    """Dois modos de falar com o Drive, e a escolha não é de gosto.

    Conta de serviço exige que ALGUÉM compartilhe a pasta com ela — e portanto
    exige ter direito de compartilhar. OAuth lê o Drive como uma pessoa, com a
    permissão que ela já tem: é a saída para pasta da organização que quem
    configura consegue ler mas não consegue compartilhar.
    """

    OAUTH = dict(
        ACERVO_DRIVE_PASTA_ID='raiz',
        ACERVO_DRIVE_CREDENCIAIS='',
        ACERVO_DRIVE_OAUTH_CLIENT_ID='cid',
        ACERVO_DRIVE_OAUTH_CLIENT_SECRET='segredo',
        ACERVO_DRIVE_OAUTH_REFRESH_TOKEN='refresh',
    )

    @patch('acervo.drive.build', object())
    @override_settings(**OAUTH)
    def test_oauth_completo_conta_como_configurado(self):
        self.assertTrue(drive.configurado())
        self.assertEqual(drive.modo_de_autenticacao(), 'OAuth de usuário')

    @patch('acervo.drive.build', object())
    @override_settings(**{**OAUTH, 'ACERVO_DRIVE_OAUTH_REFRESH_TOKEN': ''})
    def test_oauth_pela_metade_nao_conta(self):
        """Faltando uma das três, o Drive fica desligado — e diz o que falta.

        Meio configurado é pior que desligado: falharia só na hora do envio.
        """
        self.assertFalse(drive.configurado())
        self.assertIn('ACERVO_DRIVE_OAUTH', drive.motivo_de_estar_desligado())

    @patch('acervo.drive.build', object())
    @override_settings(ACERVO_DRIVE_PASTA_ID='raiz',
                       ACERVO_DRIVE_CREDENCIAIS='/tmp/sa.json')
    def test_conta_de_servico_sozinha_basta(self):
        self.assertTrue(drive.configurado())
        self.assertEqual(drive.modo_de_autenticacao(), 'conta de serviço')

    @patch('acervo.drive.build', object())
    @override_settings(**{**OAUTH, 'ACERVO_DRIVE_CREDENCIAIS': '/tmp/sa.json'})
    def test_conta_de_servico_tem_precedencia(self):
        """Com os dois configurados, um tem que vencer de forma previsível."""
        self.assertEqual(drive.modo_de_autenticacao(), 'conta de serviço')

    @patch('acervo.drive.build', object())
    @override_settings(**{**OAUTH, 'ACERVO_DRIVE_PASTA_ID': ''})
    def test_sem_a_pasta_nao_adianta_ter_credencial(self):
        self.assertFalse(drive.configurado())
        self.assertIn('ACERVO_DRIVE_PASTA_ID', drive.motivo_de_estar_desligado())

    @patch('acervo.drive.build', object())
    @patch('acervo.drive.Credentials')
    @override_settings(**OAUTH)
    def test_a_credencial_oauth_guarda_so_o_refresh_token(self, fake):
        """O access token dura 1 hora — guardá-lo no .env seria inútil.

        A biblioteca obtém um novo a cada uso, a partir do refresh token.
        """
        drive._credenciais()
        self.assertIsNone(fake.call_args.kwargs['token'])
        self.assertEqual(fake.call_args.kwargs['refresh_token'], 'refresh')
