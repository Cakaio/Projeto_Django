"""Testes do comando `importar_acervo` — a migração do Drive para o Acervo.

O comando é a ponte entre uma árvore de pastas baixada do Google Drive e o
modelo do Acervo. O que erra numa importação em lote é sempre a mesma coisa:
trazer o que não devia, duplicar ao rodar de novo, e inventar dado que ninguém
conferiu. É isso que estes testes travam.
"""
import shutil
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from io import StringIO

from acervo.models import Colecao, Documento

# A migration 0002 semeia a coleção "Postulações". Ela existe em qualquer banco,
# inclusive o de teste — as asserções sobre quais coleções existem precisam
# descontá-la, senão testam o seed em vez do comando.
COLECAO_SEMEADA = 'Postulações'


class BaseImportacao(TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix='drive-'))
        self.media = Path(tempfile.mkdtemp(prefix='media-'))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

        # Vale para o TESTE INTEIRO, não só para a chamada do comando: ler
        # `documento.arquivo` depois da importação também passa pelo storage, e
        # com o override só em volta do call_command a leitura caía no
        # MEDIA_ROOT de verdade — e a suíte escreveria no media/ do projeto.
        self._media_falsa = override_settings(MEDIA_ROOT=str(self.media))
        self._media_falsa.enable()
        self.addCleanup(self._media_falsa.disable)

    def arquivo(self, caminho_relativo, conteudo=b'conteudo de teste'):
        destino = self.raiz / caminho_relativo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        return destino

    def colecoes_criadas(self):
        """Coleções que o comando criou — sem a que a migration já semeia."""
        return set(Colecao.objects.exclude(nome=COLECAO_SEMEADA)
                   .values_list('nome', flat=True))

    def importar(self, *extras):
        saida = StringIO()
        call_command('importar_acervo', str(self.raiz), *extras,
                     stdout=saida, stderr=saida)
        return saida.getvalue()


class EstruturaTest(BaseImportacao):

    def test_cada_subpasta_vira_uma_colecao(self):
        self.arquivo('Postulações 2023/joao.pdf')
        self.arquivo('Atas 2024/reuniao.pdf')
        self.importar('--nome-padrao', 'Acervo do projeto')

        self.assertEqual(self.colecoes_criadas(),
                         {'Postulações 2023', 'Atas 2024'})

    def test_arquivos_em_subpastas_profundas_entram_na_colecao_do_topo(self):
        self.arquivo('Postulações 2023/eleitos/joao.pdf')
        self.arquivo('Postulações 2023/nao-eleitos/maria.pdf')
        self.importar('--nome-padrao', 'Acervo do projeto')

        colecao = Colecao.objects.get(nome='Postulações 2023')
        self.assertEqual(colecao.documentos.count(), 2)

    def test_arquivo_solto_na_raiz_e_ignorado_com_aviso(self):
        self.arquivo('Atas 2024/reuniao.pdf')
        self.arquivo('perdido.pdf')
        saida = self.importar('--nome-padrao', 'Acervo do projeto')

        self.assertIn('solto', saida)
        self.assertEqual(Documento.objects.count(), 1)

    def test_pasta_sem_subpasta_nenhuma_falha_explicando(self):
        self.arquivo('so-um-arquivo.pdf')
        with self.assertRaises(CommandError) as erro:
            self.importar('--nome-padrao', 'x')
        self.assertIn('subpasta', str(erro.exception))

    def test_somente_limita_as_pastas_escolhidas(self):
        """A liderança decide pasta por pasta o que entra no acervo."""
        self.arquivo('Postulações 2023/joao.pdf')
        self.arquivo('Financeiro 2024/extrato.pdf')
        self.importar('--nome-padrao', 'Acervo', '--somente', 'Postulações 2023')

        self.assertEqual(self.colecoes_criadas(), {'Postulações 2023'})
        self.assertEqual(Documento.objects.count(), 1)


class AnoTest(BaseImportacao):

    def test_ano_sai_do_nome_do_arquivo(self):
        self.arquivo('Atas/reuniao-2021.pdf')
        self.importar('--nome-padrao', 'Acervo')
        self.assertEqual(Documento.objects.get().ano, 2021)

    def test_ano_do_arquivo_vence_o_da_pasta(self):
        """"ata-2023.pdf" dentro de "Postulações 2019/" é de 2023."""
        self.arquivo('Postulações 2019/ata-2023.pdf')
        self.importar('--nome-padrao', 'Acervo')
        self.assertEqual(Documento.objects.get().ano, 2023)

    def test_ano_cai_para_a_pasta_quando_o_arquivo_nao_tem(self):
        self.arquivo('Postulações 2019/joao.pdf')
        self.importar('--nome-padrao', 'Acervo')
        self.assertEqual(Documento.objects.get().ano, 2019)

    def test_sem_ano_em_lugar_nenhum_o_arquivo_e_pulado(self):
        self.arquivo('Atas/reuniao.pdf')
        saida = self.importar('--nome-padrao', 'Acervo')
        self.assertIn('sem ano', saida)
        self.assertEqual(Documento.objects.count(), 0)

    def test_ano_padrao_resolve_quem_nao_tem(self):
        self.arquivo('Atas/reuniao.pdf')
        self.importar('--nome-padrao', 'Acervo', '--ano', '2020')
        self.assertEqual(Documento.objects.get().ano, 2020)

    def test_numero_que_nao_e_ano_nao_vira_ano(self):
        """"2 vias" ou um telefone no nome não podem virar o ano do documento."""
        self.arquivo('Atas/documento-12345.pdf')
        saida = self.importar('--nome-padrao', 'Acervo')
        self.assertIn('sem ano', saida)


class FiltrosTest(BaseImportacao):

    def test_formato_nao_aceito_e_pulado(self):
        self.arquivo('Atas 2024/planilha.xlsx')
        saida = self.importar('--nome-padrao', 'Acervo')
        self.assertIn('não aceito', saida)
        self.assertEqual(Documento.objects.count(), 0)

    def test_arquivo_acima_do_limite_e_pulado(self):
        self.arquivo('Atas 2024/enorme.pdf', b'x' * (16 * 1024 * 1024))
        saida = self.importar('--nome-padrao', 'Acervo')
        self.assertIn('limite', saida)
        self.assertEqual(Documento.objects.count(), 0)

    def test_sem_nome_padrao_os_documentos_sao_pulados(self):
        """Documento.clean() exige dizer de quem é.

        Numa importação em lote não há como saber, e inventar um nome seria
        pior que não importar: viraria dado falso dentro do acervo.
        """
        self.arquivo('Atas 2024/reuniao.pdf')
        saida = self.importar()
        self.assertIn('de quem é', saida)
        self.assertEqual(Documento.objects.count(), 0)


class DryRunTest(BaseImportacao):

    def test_dry_run_nao_grava_nada(self):
        self.arquivo('Postulações 2023/joao.pdf')
        saida = self.importar('--nome-padrao', 'Acervo', '--dry-run')

        self.assertEqual(Documento.objects.count(), 0)
        self.assertEqual(self.colecoes_criadas(), set())
        self.assertIn('NADA foi gravado', saida)

    def test_dry_run_mostra_o_que_entraria(self):
        self.arquivo('Postulações 2023/joao.pdf')
        saida = self.importar('--nome-padrao', 'Acervo', '--dry-run')
        self.assertIn('joao', saida)
        self.assertIn('2023', saida)

    def test_dry_run_soma_o_tamanho_total(self):
        """Antes de copiar, a liderança precisa saber quanto disco vai ocupar."""
        self.arquivo('Atas 2024/a.pdf', b'x' * (2 * 1024 * 1024))
        self.arquivo('Atas 2024/b.pdf', b'x' * (3 * 1024 * 1024))
        saida = self.importar('--nome-padrao', 'Acervo', '--dry-run')
        self.assertIn('5.0 MB', saida)


class IdempotenciaTest(BaseImportacao):

    def test_rodar_duas_vezes_nao_duplica(self):
        self.arquivo('Postulações 2023/joao.pdf')
        self.importar('--nome-padrao', 'Acervo')
        saida = self.importar('--nome-padrao', 'Acervo')

        self.assertEqual(Documento.objects.count(), 1)
        self.assertIn('já está no acervo', saida)

    def test_colecao_existente_e_reaproveitada(self):
        Colecao.objects.create(nome='Postulações 2023', descricao='Já existia')
        self.arquivo('Postulações 2023/joao.pdf')
        self.importar('--nome-padrao', 'Acervo')

        self.assertEqual(Colecao.objects.filter(nome='Postulações 2023').count(), 1)
        self.assertEqual(
            Colecao.objects.get(nome='Postulações 2023').descricao, 'Já existia')


class ConteudoTest(BaseImportacao):

    def test_o_arquivo_e_copiado_de_verdade(self):
        self.arquivo('Postulações 2023/joao.pdf', b'PDF do Joao')
        self.importar('--nome-padrao', 'Acervo')

        documento = Documento.objects.get()
        self.assertEqual(documento.arquivo.read(), b'PDF do Joao')

    def test_o_arquivo_vai_para_a_pasta_protegida_por_login(self):
        """O prefixo `acervo/` é o que faz a view `midia` exigir sessão."""
        self.arquivo('Postulações 2023/joao.pdf')
        self.importar('--nome-padrao', 'Acervo')

        self.assertTrue(Documento.objects.get().arquivo.name.startswith('acervo/'))

    def test_titulo_legivel_a_partir_do_nome_do_arquivo(self):
        self.arquivo('Atas/ata_reuniao-geral_2023.pdf')
        self.importar('--nome-padrao', 'Acervo')
        self.assertEqual(Documento.objects.get().titulo, 'ata reuniao geral 2023')

    def test_a_origem_fica_registrada_na_descricao(self):
        """Depois de importar, precisa dar para saber de onde o arquivo veio."""
        self.arquivo('Postulações 2023/eleitos/joao.pdf')
        self.importar('--nome-padrao', 'Acervo')
        self.assertIn('Postulações 2023/eleitos/joao.pdf',
                      Documento.objects.get().descricao)

    def test_enviado_por_registra_quem_rodou(self):
        from voluntario.models import Voluntario

        vinicius = Voluntario.objects.create_user(
            username='vinicius', password='senha-de-teste-123', area='TRIADE')
        self.arquivo('Postulações 2023/joao.pdf')
        self.importar('--nome-padrao', 'Acervo', '--enviado-por', 'vinicius')

        self.assertEqual(Documento.objects.get().enviado_por, vinicius)

    def test_enviado_por_inexistente_falha_cedo(self):
        self.arquivo('Postulações 2023/joao.pdf')
        with self.assertRaises(CommandError):
            self.importar('--nome-padrao', 'Acervo', '--enviado-por', 'ninguem')
        self.assertEqual(Documento.objects.count(), 0)


class ResumoTest(BaseImportacao):
    """--resumo: uma linha por coleção, para levantar pasta grande.

    Numa árvore com centenas de arquivos, a listagem arquivo a arquivo vira
    ruído e a pergunta que importa ("por que só metade entrou?") fica enterrada.
    """

    def test_resumo_nao_lista_arquivo_por_arquivo(self):
        self.arquivo('Atas 2024/reuniao-um.pdf')
        self.arquivo('Atas 2024/reuniao-dois.pdf')
        saida = self.importar('--nome-padrao', 'Acervo', '--dry-run', '--resumo')

        self.assertNotIn('reuniao-um', saida)
        self.assertIn('2 documento(s)', saida)

    def test_resumo_agrupa_os_motivos_de_exclusao(self):
        self.arquivo('Atas 2024/a.xlsx')
        self.arquivo('Atas 2024/b.xlsx')
        self.arquivo('Atas 2024/c.pdf')
        saida = self.importar('--nome-padrao', 'Acervo', '--dry-run', '--resumo')

        self.assertIn('2x formato .xlsx não aceito', saida)

    def test_o_modo_detalhado_continua_listando_arquivo(self):
        self.arquivo('Atas 2024/reuniao-um.pdf')
        saida = self.importar('--nome-padrao', 'Acervo', '--dry-run')
        self.assertIn('reuniao-um', saida)

    def test_resumo_mostra_o_tamanho_por_colecao(self):
        """É o número que decide se cabe no disco do servidor."""
        self.arquivo('Atas 2024/a.pdf', b'x' * (2 * 1024 * 1024))
        self.arquivo('Fotos 2023/b.pdf', b'x' * (4 * 1024 * 1024))
        saida = self.importar('--nome-padrao', 'Acervo', '--dry-run', '--resumo')

        self.assertIn('2.0 MB', saida)
        self.assertIn('4.0 MB', saida)
        self.assertIn('6.0 MB', saida)   # o total


class ColecaoVaziaTest(BaseImportacao):
    """Pasta em que nada entrou não pode deixar coleção vazia no acervo.

    Acontece de verdade: uma pasta só de vídeo, ou sem ano em lugar nenhum,
    tem todos os arquivos pulados — e a tela ficaria com uma coleção que não
    abre nada.
    """

    def test_pasta_com_tudo_pulado_nao_cria_colecao(self):
        self.arquivo('Fotos do Sábado/video.mp4')
        self.arquivo('Fotos do Sábado/foto.jpg')   # sem ano em lugar nenhum
        saida = self.importar('--nome-padrao', 'Acervo')

        self.assertEqual(self.colecoes_criadas(), set())
        self.assertIn('não criada', saida)

    def test_pasta_com_um_arquivo_valido_cria_a_colecao(self):
        self.arquivo('Atas 2024/video.mp4')
        self.arquivo('Atas 2024/ata.pdf')
        self.importar('--nome-padrao', 'Acervo')

        self.assertEqual(self.colecoes_criadas(), {'Atas 2024'})

    def test_colecao_que_ja_existia_nao_e_apagada(self):
        """Só apaga o que este comando acabou de criar."""
        Colecao.objects.create(nome='Fotos do Sábado', descricao='Já existia')
        self.arquivo('Fotos do Sábado/video.mp4')
        self.importar('--nome-padrao', 'Acervo')

        self.assertTrue(Colecao.objects.filter(nome='Fotos do Sábado').exists())
