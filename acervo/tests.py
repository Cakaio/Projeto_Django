"""Testes do acervo.

As views que renderizam página são chamadas direto pelo RequestFactory, sem
`self.client`: o test client copia o contexto do template e essa cópia quebra no
Python 3.14 (o Django 4.2 só suporta até o 3.12). É falha do ambiente, não do
app — e chamando a view direto os templates DE VERDADE são exercitados.
"""
import shutil
import tempfile

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from voluntario.models import Voluntario

from . import views
from .forms import TAMANHO_MAXIMO_MB, DocumentoForm
from .models import Colecao, Documento, caminho_do_documento


def arquivo(nome='ficha.pdf', tamanho=10):
    return SimpleUploadedFile(nome, b'x' * tamanho, content_type='application/pdf')


class MediaIsolada(TestCase):
    """Base para teste que grava arquivo.

    Sem isto cada rodada da suite deixa um .pdf orfao em media/acervo/ do
    projeto: a transacao do TestCase desfaz a linha no banco, mas nao apaga o
    arquivo que o FileField ja escreveu no disco. Eram mais de 30 acumulados
    quando isto foi notado.
    """

    def setUp(self):
        super().setUp()
        pasta = tempfile.mkdtemp(prefix='acervo-teste-')
        self.addCleanup(shutil.rmtree, pasta, ignore_errors=True)
        self._media = override_settings(MEDIA_ROOT=pasta)
        self._media.enable()
        self.addCleanup(self._media.disable)


class ColecaoInicialTests(TestCase):
    """A coleção de postulações entra pela migração 0002."""

    def test_o_acervo_nao_abre_vazio_no_deploy(self):
        colecao = Colecao.objects.get(slug='postulacoes')
        self.assertEqual(colecao.nome, 'Postulações')
        self.assertTrue(colecao.ativo)
        self.assertIn('eleito', colecao.descricao)


class CaminhoDoArquivoTests(TestCase):
    """O prefixo `acervo/` é o que faz a view `midia` exigir sessão."""

    def test_arquivo_fica_sob_acervo_e_dentro_da_colecao(self):
        colecao = Colecao.objects.get(slug='postulacoes')
        documento = Documento(colecao=colecao, titulo='Ficha', ano=2025)
        self.assertEqual(
            caminho_do_documento(documento, 'ficha.pdf'),
            'acervo/postulacoes/ficha.pdf',
        )

    def test_prefixo_nao_esta_entre_as_pastas_publicas(self):
        """Se `acervo/` virasse pasta pública, documento de postulação abriria
        por link solto para qualquer pessoa da internet."""
        from TESTE.views import PASTAS_DE_MIDIA_PUBLICA
        self.assertFalse('acervo/postulacoes/x.pdf'.startswith(PASTAS_DE_MIDIA_PUBLICA))


class PermissaoTests(TestCase):
    """Ler é de todo voluntário logado; mexer é da Tríade."""

    @classmethod
    def setUpTestData(cls):
        cls.colecao = Colecao.objects.get(slug='postulacoes')
        cls.comum = Voluntario.objects.create_user(
            username='comum', password='x', area='VIOLETA', first_name='Ana')
        cls.triade = Voluntario.objects.create_user(
            username='triade', password='x', area='TRIADE', first_name='Bia')
        cls.chefe = Voluntario.objects.create_superuser(
            username='chefe', password='x', email='c@pcf.org')

    def setUp(self):
        self.fabrica = RequestFactory()

    def _get(self, rota, usuario, **kwargs):
        pedido = self.fabrica.get(rota)
        pedido.user = usuario
        return pedido

    def test_voluntario_comum_le_a_lista(self):
        resposta = views.lista(self._get(reverse('acervo:lista'), self.comum))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('Postulações', resposta.content.decode())

    def test_voluntario_comum_le_a_colecao(self):
        pedido = self._get(reverse('acervo:colecao', args=['postulacoes']), self.comum)
        resposta = views.colecao(pedido, slug='postulacoes')
        self.assertEqual(resposta.status_code, 200)

    def test_voluntario_comum_nao_ve_botao_de_cadastrar(self):
        """Mostrar o botão para quem toma 403 ao clicar é convite a frustração."""
        html = views.lista(self._get(reverse('acervo:lista'), self.comum)).content.decode()
        self.assertNotIn('Novo documento', html)

    def test_voluntario_comum_nao_cadastra(self):
        pedido = self._get(reverse('acervo:documento_criar'), self.comum)
        with self.assertRaises(PermissionDenied):
            views.documento_form(pedido)

    def test_triade_cadastra(self):
        pedido = self._get(reverse('acervo:documento_criar'), self.triade)
        self.assertEqual(views.documento_form(pedido).status_code, 200)

    def test_superusuario_cadastra(self):
        pedido = self._get(reverse('acervo:documento_criar'), self.chefe)
        self.assertEqual(views.documento_form(pedido).status_code, 200)

    def test_ano_nao_numerico_na_url_nao_estoura(self):
        """`?ano=abc` chegaria no queryset como int() e viraria erro 500."""
        pedido = self.fabrica.get(
            reverse('acervo:colecao', args=['postulacoes']), {'ano': 'abc'})
        pedido.user = self.comum
        self.assertEqual(views.colecao(pedido, slug='postulacoes').status_code, 200)


class DocumentoModeloTests(MediaIsolada):

    @classmethod
    def setUpTestData(cls):
        cls.colecao = Colecao.objects.get(slug='postulacoes')
        cls.pessoa = Voluntario.objects.create_user(
            username='cida', password='x', area='AZUL',
            first_name='Cida', last_name='Rocha')

    def test_exige_dizer_de_quem_e_o_documento(self):
        documento = Documento(colecao=self.colecao, titulo='Carta', ano=2024)
        with self.assertRaises(ValidationError):
            documento.full_clean()

    def test_nome_digitado_serve_para_quem_nunca_teve_ficha(self):
        """Postulação de 2019 pode ser de gente que nunca teve login. Exigir
        ficha deixaria esse documento fora do acervo."""
        documento = Documento(colecao=self.colecao, titulo='Carta', ano=2019,
                              nome_avulso='Ferreira', arquivo='acervo/x.pdf')
        documento.full_clean()
        self.assertEqual(documento.de_quem, 'Ferreira')

    def test_ficha_tem_prioridade_sobre_o_nome_digitado(self):
        documento = Documento(colecao=self.colecao, titulo='Carta', ano=2024,
                              pessoa=self.pessoa, nome_avulso='errado')
        self.assertEqual(documento.de_quem, 'Cida Rocha')

    def test_selo_da_extensao_sai_do_nome_do_arquivo(self):
        documento = Documento(colecao=self.colecao, titulo='C', ano=2024,
                              arquivo='acervo/postulacoes/ficha.PDF')
        self.assertEqual(documento.extensao, 'PDF')

    def test_arquivo_sem_extensao_nao_quebra_o_selo(self):
        documento = Documento(colecao=self.colecao, titulo='C', ano=2024,
                              arquivo='acervo/postulacoes/ficha')
        self.assertEqual(documento.extensao, 'ARQUIVO')


class DocumentoFormTests(MediaIsolada):

    @classmethod
    def setUpTestData(cls):
        cls.colecao = Colecao.objects.get(slug='postulacoes')

    def dados(self, **extra):
        base = {'colecao': self.colecao.pk, 'titulo': 'Ficha de postulação',
                'ano': 2025, 'nome_avulso': 'Ferreira', 'resultado': 'NAO_ELEITO'}
        base.update(extra)
        return base

    def test_aceita_pdf(self):
        form = DocumentoForm(self.dados(), {'arquivo': arquivo('ficha.pdf')})
        self.assertTrue(form.is_valid(), form.errors)

    def test_recusa_formato_fora_da_lista(self):
        """Upload livre num acervo aberto a todo voluntário é porta para
        arquivo que ninguém deveria estar servindo."""
        form = DocumentoForm(self.dados(), {'arquivo': arquivo('script.exe')})
        self.assertFalse(form.is_valid())
        self.assertIn('arquivo', form.errors)

    def test_recusa_arquivo_grande(self):
        grande = arquivo('ficha.pdf', tamanho=(TAMANHO_MAXIMO_MB + 1) * 1024 * 1024)
        form = DocumentoForm(self.dados(), {'arquivo': grande})
        self.assertFalse(form.is_valid())
        self.assertIn('arquivo', form.errors)

    def test_a_lista_de_pessoas_inclui_quem_saiu_do_projeto(self):
        """O acervo é sobre quem postulou NA ÉPOCA. Filtrar por ativos deixaria
        de fora justamente o caso mais comum de documento antigo."""
        import datetime
        saiu = Voluntario.objects.create_user(
            username='saiu', password='x', area='VERDE', first_name='Dora',
            data_saida=datetime.date(2025, 1, 5), is_active=False)
        form = DocumentoForm()
        self.assertIn(saiu, form.fields['pessoa'].queryset)


class CadastroTests(MediaIsolada):

    @classmethod
    def setUpTestData(cls):
        cls.colecao = Colecao.objects.get(slug='postulacoes')
        cls.triade = Voluntario.objects.create_user(
            username='triade', password='x', area='TRIADE', first_name='Bia')

    def test_registra_quem_subiu_o_documento(self):
        """Acervo sem autoria não dá para auditar depois."""
        fabrica = RequestFactory()
        pedido = fabrica.post(reverse('acervo:documento_criar'), {
            'colecao': self.colecao.pk, 'titulo': 'Ficha', 'ano': 2025,
            'nome_avulso': 'Ferreira', 'resultado': 'ELEITO',
        })
        pedido.FILES['arquivo'] = arquivo('ficha.pdf')
        pedido.user = self.triade
        # `messages` precisa de armazenamento quando a view chama messages.success.
        from django.contrib.messages.storage.fallback import FallbackStorage
        pedido.session = {}
        pedido._messages = FallbackStorage(pedido)

        resposta = views.documento_form(pedido)

        self.assertEqual(resposta.status_code, 302)
        documento = Documento.objects.get()
        self.assertEqual(documento.enviado_por, self.triade)
        self.assertEqual(documento.colecao, self.colecao)
