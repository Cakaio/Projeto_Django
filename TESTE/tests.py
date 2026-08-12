"""Testes do que mora no pacote do projeto: hoje, o acesso aos uploads.

Por que isto existe: /media/ guarda documento de atendido, foto de criança e
comprovante de reembolso. Servir a pasta inteira sem autenticação (como já
esteve) publicava tudo isso para quem descobrisse um endereço. Ao mesmo tempo,
a revista do doador é uma página pública por design e precisa das fotos das
atividades. Estes testes travam essa fronteira, que é fácil de quebrar sem
querer numa mexida futura em urls.py.
"""
import shutil
import tempfile
from pathlib import Path

from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings

from TESTE.views import midia
from voluntario.models import Voluntario


def _pedir(endereco, usuario=None):
    """Chama a view direto. Motivo: quando a view levanta Http404, o test
    client renderiza a página de erro — e esse render quebra no Python 3.14
    com Django 4.2 (falha pré-existente do ambiente, não do app)."""
    pedido = RequestFactory().get(endereco)
    pedido.user = usuario or AnonymousUser()
    return midia(pedido, endereco.removeprefix('/media/'))


PASTA_TEMPORARIA = tempfile.mkdtemp(prefix='pcf-midia-')


def _criar(caminho_relativo, conteudo='conteudo'):
    destino = Path(PASTA_TEMPORARIA) / caminho_relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding='utf-8')
    return '/media/' + caminho_relativo


@override_settings(MEDIA_ROOT=PASTA_TEMPORARIA)
class AcessoAMidiaTests(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.foto_revista = _criar('fotos_atividades/roda-de-leitura.jpg')
        cls.foto_propria = _criar('revista/capa.jpg')
        cls.documento = _criar('documentos_atendidos/rg-da-crianca.pdf')
        cls.comprovante = _criar('reembolsos/nota-fiscal.jpg')
        cls.foto_voluntario = _criar('fotos_voluntarios/livia.jpg')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(PASTA_TEMPORARIA, ignore_errors=True)
        super().tearDownClass()

    def test_fotos_da_revista_abrem_sem_login(self):
        """A página do doador não tem conta no sistema: se estas fotos
        exigissem sessão, a revista chegaria sem imagem nenhuma."""
        for endereco in (self.foto_revista, self.foto_propria):
            with self.subTest(endereco=endereco):
                self.assertEqual(self.client.get(endereco).status_code, 200)

    def test_foto_publica_sai_com_noindex(self):
        resposta = self.client.get(self.foto_revista)
        self.assertIn('noindex', resposta['X-Robots-Tag'])
        self.assertIn('noimageindex', resposta['X-Robots-Tag'])

    def test_documento_de_crianca_nao_abre_sem_login(self):
        """O caso mais grave: documento de menor de idade acessível por URL.

        404 e não 403 de propósito — 403 confirmaria que o arquivo existe."""
        with self.assertRaises(Http404):
            _pedir(self.documento)

    def test_comprovante_e_foto_de_voluntario_nao_abrem_sem_login(self):
        for endereco in (self.comprovante, self.foto_voluntario):
            with self.subTest(endereco=endereco), self.assertRaises(Http404):
                _pedir(endereco)

    def test_com_login_o_arquivo_privado_abre(self):
        usuario = Voluntario.objects.create_user(
            username='livia', password='senha-de-teste', first_name='Livia', area='CR/RE')
        for endereco in (self.documento, self.comprovante, self.foto_voluntario):
            with self.subTest(endereco=endereco):
                self.assertEqual(_pedir(endereco, usuario).status_code, 200)

    def test_nao_da_para_escapar_da_pasta_publica(self):
        """Travessia de diretório: 'fotos_atividades/..' aponta para uma pasta
        pública mas resolve para uma privada. Sem normalizar o caminho antes de
        conferir o prefixo, a pasta pública vira porta dos fundos para todo o
        /media/ — inclusive para o documento da criança."""
        for fuga in ('/media/fotos_atividades/../documentos_atendidos/rg-da-crianca.pdf',
                     '/media/revista/../reembolsos/nota-fiscal.jpg',
                     '/media/fotos_atividades/../../etc/passwd'):
            with self.subTest(fuga=fuga), self.assertRaises(Http404):
                _pedir(fuga)
