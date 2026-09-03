"""Testes do robô de editais.

Nenhum teste acessa a internet: toda saída de rede passa por `requests.get`
dentro de `editais.coleta`, e é sempre ele que substituímos por um dublê.

Observação sobre RequestFactory: as views que RENDERIZAM página são chamadas
direto, sem `self.client`. O test client do Django copia o contexto do template
(`store_rendered_templates`), e essa cópia quebra no Python 3.14 — o Django 4.2
só suporta até o 3.12. É falha do ambiente, não do app.

Os templates de verdade são escritos à parte, então as views são exercitadas
com um jogo de templates de mentira (`TEMPLATES_DE_TESTE`): o que está sob
teste aqui é a permissão e o contexto, não o HTML.
"""
from datetime import date, timedelta
from io import StringIO
from unittest import mock

import requests
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import (RequestFactory, SimpleTestCase, TestCase,
                         override_settings)
from django.urls import reverse
from django.utils import timezone

from editais import coleta, views
from editais.models import ConsultaBusca, Edital, FonteEdital, PalavraChave
from voluntario.models import Voluntario

TEMPLATES_DE_TESTE = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': False,
    'OPTIONS': {
        'context_processors': [],
        'loaders': [('django.template.loaders.locmem.Loader', {
            'editais/lista.html':
                'total={{ total }}|novos={{ novos }}|'
                '{% for e in editais %}[{{ e.titulo }}]{% endfor %}',
            'editais/form.html': 'form-edital',
            'editais/fontes.html': 'fontes={{ fontes|length }}|erro={{ com_erro }}',
            'editais/fonte_form.html': 'form-fonte',
            'editais/palavras.html':
                'palavras={{ palavras|length }}|positivas={{ positivas|length }}|'
                'negativas={{ negativas|length }}',
            'editais/confirmar_exclusao.html': 'apagar {{ tipo }} {{ nome }}',
            'editais/consultas.html':
                'consultas={{ consultas|length }}|ativas={{ ativas|length }}|'
                'com_erro={{ com_erro|length }}',
        })],
    },
}]


def criar_voluntario(username, area='MARKETING', superuser=False):
    """`area` é obrigatória no model. O padrão MARKETING é de propósito: uma
    área SEM poder nenhum aqui, para provar que o acesso veio de onde
    esperamos (CR/RE, TRIADE ou is_superuser) e não da área."""
    return Voluntario.objects.create_user(
        username=username, password='senha-de-teste',
        first_name=username.capitalize(), area=area, is_superuser=superuser,
    )


def requisicao(metodo, rota, usuario, dados=None):
    """Requisição pronta para chamar a view direto, com mensagens ligadas
    (as views usam `messages`, que exige o middleware que o factory não tem)."""
    fabrica = RequestFactory()
    pedido = getattr(fabrica, metodo)(rota, dados or {})
    pedido.user = usuario
    pedido.session = {}
    setattr(pedido, '_messages', FallbackStorage(pedido))
    return pedido


class RespostaFalsa:
    """Só o que `coleta` usa de um requests.Response."""

    def __init__(self, corpo='', status=200):
        self.text = corpo
        self.content = corpo.encode('utf-8')
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'HTTP {self.status_code}')


RSS_DE_EXEMPLO = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <title>Fonte de teste</title>
  <item>
    <title>Edital de apoio à primeira infância</title>
    <link>https://fonte.org/editais/1</link>
    <description>&lt;p&gt;Para OSCs que atendem &lt;b&gt;crianças&lt;/b&gt;.&lt;/p&gt;</description>
  </item>
  <item>
    <title>Chamada de mestrado em engenharia</title>
    <link>https://fonte.org/editais/2</link>
    <description>Bolsa de pesquisa.</description>
  </item>
</channel></rss>
"""

HTML_DE_EXEMPLO = """
<html><body>
  <div class="lista">
    <article class="edital">
      <h2><a href="/editais/10">Chamada para projetos com adolescentes</a></h2>
      <p class="resumo">Contraturno escolar em comunidade.</p>
    </article>
    <article class="edital">
      <h2><a href="https://outra.org/edital/20">Fomento a startups</a></h2>
      <p class="resumo">Inovação tecnológica.</p>
    </article>
  </div>
</body></html>
"""


# ────────────────────────────── Permissão ──────────────────────────────
@override_settings(TEMPLATES=TEMPLATES_DE_TESTE)
class PermissaoEditaisTests(TestCase):
    """A tela de editais é do CR/RE, da Tríade e do superusuário — mais ninguém."""

    @classmethod
    def setUpTestData(cls):
        cls.cr = criar_voluntario('livia', area='CR/RE')
        cls.triade = criar_voluntario('tri', area='TRIADE')
        cls.admin = criar_voluntario('root', superuser=True)
        cls.comum = criar_voluntario('zeca', area='RECREACAO')

    def telas(self):
        return [
            (reverse('editais:lista'), views.lista),
            (reverse('editais:criar'), views.criar),
            (reverse('editais:fontes'), views.fontes),
            (reverse('editais:fonte_criar'), views.fonte_form),
            (reverse('editais:palavras'), views.palavras),
        ]

    def test_cr_re_tem_acesso(self):
        for rota, view in self.telas():
            resposta = view(requisicao('get', rota, self.cr))
            self.assertEqual(resposta.status_code, 200, rota)

    def test_triade_e_superuser_tem_acesso(self):
        for usuario in (self.triade, self.admin):
            resposta = views.lista(requisicao('get', reverse('editais:lista'), usuario))
            self.assertEqual(resposta.status_code, 200)

    def test_voluntario_de_outra_area_recebe_403(self):
        for rota, view in self.telas():
            with self.assertRaises(PermissionDenied, msg=rota):
                view(requisicao('get', rota, self.comum))

    def test_anonimo_e_redirecionado_para_login(self):
        resposta = self.client.get(reverse('editais:lista'))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/login', resposta.url)


# ────────────────────────────── Pontuação ──────────────────────────────
class PontuacaoTests(TestCase):
    """A nota é a única coisa que separa 'edital que serve' de ruído."""

    def palavra(self, termo, peso=3, ativo=True):
        # update_or_create porque a migração 0002 já semeia parte destes termos:
        # o teste quer o termo com ESTE peso, exista ele ou não.
        obj, _ = PalavraChave.objects.update_or_create(
            termo=termo, defaults={'peso': peso, 'ativo': ativo})
        return obj

    def test_acento_e_caixa_nao_atrapalham(self):
        palavras = [self.palavra('criança', 3)]
        nota, termos = coleta.pontuar('', 'Projetos para CRIANCAS em risco', palavras)
        self.assertEqual(nota, 3)
        self.assertEqual(termos, ['criança'])

    def test_termo_sem_acento_acha_texto_com_acento(self):
        """O CR pode cadastrar de qualquer jeito; os dois lados são normalizados."""
        palavras = [self.palavra('educacao', 2)]
        nota, _ = coleta.pontuar('', 'Apoio à educação básica', palavras)
        self.assertEqual(nota, 2)

    def test_palavra_no_titulo_vale_o_dobro(self):
        palavras = [self.palavra('criança', 3)]
        no_titulo, _ = coleta.pontuar('Edital criança feliz', '', palavras)
        na_descricao, _ = coleta.pontuar('', 'Edital criança feliz', palavras)
        self.assertEqual(no_titulo, 6)
        self.assertEqual(na_descricao, 3)
        self.assertEqual(no_titulo, na_descricao * coleta.PESO_TITULO)

    def test_palavra_negativa_derruba_a_nota(self):
        palavras = [self.palavra('criança', 3), self.palavra('mestrado', -3)]
        so_boa, _ = coleta.pontuar('', 'Projeto com crianças', palavras)
        com_ruim, termos = coleta.pontuar('', 'Projeto com crianças e bolsa de mestrado', palavras)
        self.assertEqual(so_boa, 3)
        self.assertEqual(com_ruim, 0)               # 3 pela boa, -3 pela ruim
        self.assertCountEqual(termos, ['criança', 'mestrado'])

    def test_negativa_no_titulo_tambem_dobra(self):
        palavras = [self.palavra('mestrado', -3)]
        nota, _ = coleta.pontuar('Edital de mestrado', 'Para crianças', palavras)
        self.assertEqual(nota, -6)

    def test_cada_termo_conta_uma_vez_so(self):
        """Repetir a palavra é estilo de quem escreve, não relevância."""
        palavras = [self.palavra('criança', 3)]
        nota, termos = coleta.pontuar('criança criança criança', 'criança', palavras)
        self.assertEqual(nota, 6)
        self.assertEqual(termos, ['criança'])

    def test_titulo_e_descricao_nao_somam_para_o_mesmo_termo(self):
        palavras = [self.palavra('criança', 3)]
        nota, _ = coleta.pontuar('Edital criança', 'para criança', palavras)
        self.assertEqual(nota, 6)                   # o dobro do título, e só

    def test_termo_nao_casa_dentro_de_outra_palavra(self):
        """'OSC' não pode achar 'oscilação' — nota inventada mina a confiança."""
        palavras = [self.palavra('OSC', 2)]
        nota, termos = coleta.pontuar('', 'Estudo sobre oscilação de preços', palavras)
        self.assertEqual((nota, termos), (0, []))

    def test_plural_simples_ainda_casa(self):
        palavras = [self.palavra('adolescente', 3)]
        nota, _ = coleta.pontuar('', 'Oficinas com adolescentes', palavras)
        self.assertEqual(nota, 3)

    def test_termo_de_duas_palavras(self):
        palavras = [self.palavra('primeira infância', 3)]
        self.assertEqual(coleta.pontuar('', 'apoio à primeira infância', palavras)[0], 3)
        self.assertEqual(coleta.pontuar('', 'apoio à infância', palavras)[0], 0)

    def test_sem_lista_usa_as_palavras_ativas_do_banco(self):
        self.palavra('criança', 3, ativo=True)
        self.palavra('mestrado', -3, ativo=False)
        nota, termos = coleta.pontuar('', 'Criança e mestrado no mesmo texto')
        self.assertEqual(nota, 3)                   # a inativa não entra na conta
        self.assertEqual(termos, ['criança'])


# ────────────────────────────── Coleta ──────────────────────────────
class ColetaFonteTests(TestCase):
    """`coletar_fonte` é o único ponto que fala com a internet — e ele não pode
    deixar exceção escapar."""

    def setUp(self):
        self.rss = FonteEdital.objects.create(
            nome='Fonte RSS', url='https://fonte.org/feed', tipo='RSS')
        self.html = FonteEdital.objects.create(
            nome='Fonte HTML', url='https://fonte.org/lista', tipo='HTML',
            seletor_item='article.edital', seletor_titulo='h2 a',
            seletor_link='h2 a', seletor_descricao='p.resumo')

    def test_erro_de_rede_nao_derruba_a_coleta(self):
        with mock.patch('editais.coleta.requests.get',
                        side_effect=requests.ConnectionError('sem rota para o host')):
            itens = coleta.coletar_fonte(self.rss)

        self.assertEqual(itens, [])                 # devolveu vazio, não levantou
        self.rss.refresh_from_db()
        self.assertIn('sem rota para o host', self.rss.ultimo_erro)
        self.assertEqual(self.rss.itens_ultima_coleta, 0)
        self.assertIsNotNone(self.rss.ultima_coleta)
        self.assertFalse(self.rss.saudavel)

    def test_erro_http_tambem_e_engolido(self):
        with mock.patch('editais.coleta.requests.get', return_value=RespostaFalsa('', status=503)):
            self.assertEqual(coleta.coletar_fonte(self.html), [])
        self.html.refresh_from_db()
        self.assertIn('503', self.html.ultimo_erro)

    def test_html_quebrado_nao_levanta(self):
        """Seletor inválido é erro de cadastro, não motivo para parar tudo."""
        self.html.seletor_item = 'article[['
        self.html.save(update_fields=['seletor_item'])
        with mock.patch('editais.coleta.requests.get', return_value=RespostaFalsa(HTML_DE_EXEMPLO)):
            self.assertEqual(coleta.coletar_fonte(self.html), [])
        self.html.refresh_from_db()
        self.assertTrue(self.html.ultimo_erro)

    def test_rss_le_titulo_link_e_descricao_sem_html(self):
        with mock.patch('editais.coleta.requests.get',
                        return_value=RespostaFalsa(RSS_DE_EXEMPLO)) as buscar:
            itens = coleta.coletar_fonte(self.rss)

        # Toda saída de rede tem prazo: sem isso a tarefa agendada trava.
        self.assertEqual(buscar.call_args.kwargs['timeout'], coleta.TEMPO_LIMITE)
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0]['titulo'], 'Edital de apoio à primeira infância')
        self.assertEqual(itens[0]['link'], 'https://fonte.org/editais/1')
        self.assertEqual(itens[0]['descricao'], 'Para OSCs que atendem crianças .')

    def test_html_usa_os_seletores_e_resolve_link_relativo(self):
        with mock.patch('editais.coleta.requests.get', return_value=RespostaFalsa(HTML_DE_EXEMPLO)):
            itens = coleta.coletar_fonte(self.html)

        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0]['titulo'], 'Chamada para projetos com adolescentes')
        self.assertEqual(itens[0]['link'], 'https://fonte.org/editais/10')   # href era "/editais/10"
        self.assertEqual(itens[0]['descricao'], 'Contraturno escolar em comunidade.')
        self.assertEqual(itens[1]['link'], 'https://outra.org/edital/20')    # absoluto fica igual

    def test_coleta_boa_limpa_o_erro_anterior(self):
        self.rss.ultimo_erro = 'timeout de ontem'
        self.rss.save(update_fields=['ultimo_erro'])
        with mock.patch('editais.coleta.requests.get', return_value=RespostaFalsa(RSS_DE_EXEMPLO)):
            coleta.coletar_fonte(self.rss)
        self.rss.refresh_from_db()
        self.assertEqual(self.rss.ultimo_erro, '')
        self.assertEqual(self.rss.itens_ultima_coleta, 2)
        self.assertTrue(self.rss.saudavel)

    def test_limite_corta_a_lista(self):
        with mock.patch('editais.coleta.requests.get', return_value=RespostaFalsa(RSS_DE_EXEMPLO)):
            itens = coleta.coletar_fonte(self.rss, limite=1)
        self.assertEqual(len(itens), 1)


# ────────────────────────────── Comando ──────────────────────────────
class BuscarEditaisTests(TestCase):

    def setUp(self):
        self.fonte = FonteEdital.objects.create(
            nome='Fonte RSS', url='https://fonte.org/feed', tipo='RSS', ativo=True)
        # Dicionário controlado: a migração 0002 semeia dezenas de termos, e com
        # eles no banco a nota destes casos deixaria de ser previsível.
        PalavraChave.objects.all().delete()
        PalavraChave.objects.create(termo='criança', peso=3)
        PalavraChave.objects.create(termo='mestrado', peso=-3)

    def rodar(self, itens, **opcoes):
        saida = StringIO()
        with mock.patch('editais.coleta.coletar_fonte', return_value=itens):
            call_command('buscar_editais', stdout=saida, stderr=saida, **opcoes)
        return saida.getvalue()

    def item(self, titulo='Edital criança feliz', link='https://fonte.org/e/1', descricao=''):
        return {'titulo': titulo, 'descricao': descricao, 'link': link}

    def test_guarda_edital_relevante(self):
        self.rodar([self.item()])
        edital = Edital.objects.get()
        self.assertEqual(edital.titulo, 'Edital criança feliz')
        self.assertEqual(edital.relevancia, 6)          # no título, peso dobrado
        self.assertEqual(edital.termos_encontrados, 'criança')
        self.assertEqual(edital.origem, 'ROBO')
        self.assertEqual(edital.fonte, self.fonte)
        self.assertEqual(edital.status, 'NOVO')

    def test_ignora_quem_nao_alcanca_a_nota_minima(self):
        self.rodar([self.item(titulo='Edital de mestrado em engenharia',
                              link='https://fonte.org/e/9')])
        self.assertFalse(Edital.objects.exists())

    def test_minimo_configuravel(self):
        itens = [self.item(titulo='Chamada para escolas',
                           descricao='Atividades com criança', link='https://fonte.org/e/3')]
        self.rodar(itens, minimo=5)                     # nota seria 3
        self.assertFalse(Edital.objects.exists())
        self.rodar(itens, minimo=3)
        self.assertTrue(Edital.objects.exists())

    def test_mesmo_link_duas_vezes_vira_um_registro_so(self):
        """O mesmo edital sai em vários lugares e o robô roda todo dia."""
        repetido = self.item(link='https://fonte.org/e/7')
        self.rodar([repetido, dict(repetido, titulo='Edital criança feliz (2ª chamada)')])
        self.assertEqual(Edital.objects.count(), 1)

        self.rodar([repetido])                          # e no dia seguinte também não duplica
        self.assertEqual(Edital.objects.count(), 1)

    def test_link_igual_com_caixa_diferente_tambem_dedupe(self):
        self.rodar([self.item(link='https://Fonte.org/E/8')])
        self.rodar([self.item(link='https://fonte.org/e/8 ')])
        self.assertEqual(Edital.objects.count(), 1)

    def test_nao_sobrescreve_o_trabalho_humano(self):
        responsavel = criar_voluntario('livia', area='CR/RE')
        existente = Edital.objects.create(
            titulo='Título revisado pelo CR', link='https://fonte.org/e/1',
            status='INSCRITO', observacoes='Conversei com a Ana, ela cuida do anexo III.',
            requisitos='CNPJ há 2 anos + certidão negativa', responsavel=responsavel,
            relevancia=1, origem='MANUAL',
        )

        self.rodar([self.item(titulo='Edital criança feliz', link='https://fonte.org/e/1')])

        existente.refresh_from_db()
        self.assertEqual(Edital.objects.count(), 1)
        self.assertEqual(existente.status, 'INSCRITO')
        self.assertEqual(existente.observacoes, 'Conversei com a Ana, ela cuida do anexo III.')
        self.assertEqual(existente.requisitos, 'CNPJ há 2 anos + certidão negativa')
        self.assertEqual(existente.responsavel, responsavel)
        self.assertEqual(existente.titulo, 'Título revisado pelo CR')
        self.assertEqual(existente.origem, 'MANUAL')
        # A nota é do robô: essa ele pode (e deve) recalcular.
        self.assertEqual(existente.relevancia, 6)

    def test_dry_run_nao_grava(self):
        saida = self.rodar([self.item()], dry_run=True)
        self.assertFalse(Edital.objects.exists())
        self.assertIn('simulação', saida)

    def test_fonte_inativa_nao_e_varrida(self):
        self.fonte.ativo = False
        self.fonte.save(update_fields=['ativo'])
        saida = self.rodar([self.item()])
        self.assertFalse(Edital.objects.exists())
        self.assertIn('Nenhuma fonte ativa', saida)

    def test_filtro_por_nome_da_fonte(self):
        FonteEdital.objects.create(nome='Outra fonte', url='https://outra.org/feed', ativo=True)
        saida = self.rodar([self.item()], fonte='outra')
        self.assertIn('Outra fonte', saida)
        self.assertNotIn('Fonte RSS', saida)

    def test_fonte_quebrada_nao_impede_as_outras(self):
        """O erro fica registrado na fonte e o comando termina normalmente."""
        boa = FonteEdital.objects.create(nome='Fonte boa', url='https://boa.org/feed', ativo=True)

        def coletar(fonte, limite=60):
            if fonte.pk == self.fonte.pk:
                fonte.ultimo_erro = 'ConnectionError: sem rota para o host'
                fonte.save(update_fields=['ultimo_erro'])
                return []
            return [self.item()]

        saida = StringIO()
        with mock.patch('editais.coleta.coletar_fonte', side_effect=coletar):
            call_command('buscar_editais', stdout=saida, stderr=saida)

        self.assertEqual(Edital.objects.count(), 1)
        self.assertEqual(Edital.objects.get().fonte, boa)
        self.assertIn('sem rota para o host', saida.getvalue())
        self.assertIn('1 fonte(s) com erro', saida.getvalue())


class SeedEditaisTests(TestCase):

    def test_cria_fontes_e_consultas(self):
        """Palavra-chave saiu daqui: agora vem da migração 0002, para o robô
        pontuar certo no deploy sem ninguém lembrar de rodar comando."""
        call_command('seed_editais', stdout=StringIO())
        # As fontes RSS foram testadas uma a uma antes de entrar no seed, por
        # isso nascem LIGADAS: o robô precisa servir no primeiro dia, sem
        # ninguém ter de descobrir onde procurar.
        self.assertTrue(FonteEdital.objects.filter(ativo=True).exists())
        # Já as reprovadas (Prosas bloqueia robô; o Mapa das OSC não publica os
        # dados) ficam registradas desligadas, para ninguém redescobrir o
        # problema.
        self.assertTrue(FonteEdital.objects.filter(ativo=False).exists())
        # Sem consulta de busca não existe varredura — e é a varredura que acha
        # edital em site que ninguém mapeou.
        self.assertTrue(ConsultaBusca.objects.filter(ativo=True).exists())

    def test_rodar_de_novo_nao_duplica(self):
        call_command('seed_editais', stdout=StringIO())
        fontes = FonteEdital.objects.count()
        consultas = ConsultaBusca.objects.count()

        call_command('seed_editais', stdout=StringIO())

        self.assertEqual(FonteEdital.objects.count(), fontes)
        self.assertEqual(ConsultaBusca.objects.count(), consultas)


# ────────────────────────────── Telas ──────────────────────────────
@override_settings(TEMPLATES=TEMPLATES_DE_TESTE)
class ListaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.cr = criar_voluntario('livia', area='CR/RE')
        Edital.objects.create(titulo='Fundo para a infância', link='https://a.org/1',
                              descricao='CMDCA municipal', status='NOVO', relevancia=9)
        Edital.objects.create(titulo='Prêmio de cultura', link='https://a.org/2',
                              status='DESCARTADO', relevancia=2)

    def abrir(self, **filtros):
        pedido = requisicao('get', reverse('editais:lista'), self.cr, filtros)
        return views.lista(pedido).content.decode()

    def test_lista_traz_tudo_por_padrao(self):
        html = self.abrir()
        self.assertIn('[Fundo para a infância]', html)
        self.assertIn('[Prêmio de cultura]', html)
        self.assertIn('total=2', html)
        self.assertIn('novos=1', html)

    def test_filtra_por_status(self):
        html = self.abrir(status='NOVO')
        self.assertIn('[Fundo para a infância]', html)
        self.assertNotIn('[Prêmio de cultura]', html)

    def test_busca_olha_titulo_e_descricao(self):
        self.assertIn('[Fundo para a infância]', self.abrir(q='infância'))
        self.assertIn('[Fundo para a infância]', self.abrir(q='CMDCA'))
        self.assertNotIn('[Prêmio de cultura]', self.abrir(q='CMDCA'))


@override_settings(TEMPLATES=TEMPLATES_DE_TESTE)
class CadastroManualTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.cr = criar_voluntario('livia', area='CR/RE')

    def test_edital_cadastrado_na_tela_nasce_manual_e_com_chave(self):
        dados = {'titulo': 'Edital do CMDCA', 'link': 'https://cmdca.org/edital',
                 'descricao': '', 'requisitos': '', 'prazo': '', 'valor': '',
                 'status': 'NOVO', 'responsavel': '', 'fonte': '', 'observacoes': ''}
        resposta = views.criar(requisicao('post', reverse('editais:criar'), self.cr, dados))

        self.assertEqual(resposta.status_code, 302)
        edital = Edital.objects.get()
        self.assertEqual(edital.origem, 'MANUAL')
        self.assertEqual(edital.chave, coleta.chave_do_link('https://cmdca.org/edital'))

    def test_recusa_link_ja_cadastrado(self):
        Edital.objects.create(titulo='Já existe', link='https://cmdca.org/edital')
        dados = {'titulo': 'Outro nome', 'link': 'https://cmdca.org/edital', 'status': 'NOVO'}
        resposta = views.criar(requisicao('post', reverse('editais:criar'), self.cr, dados))

        self.assertEqual(resposta.status_code, 200)     # voltou com erro, não gravou
        self.assertEqual(Edital.objects.count(), 1)


# ──────────────────────── Varredura na web ────────────────────────
class VarreduraTests(TestCase):
    """A varredura é a perna que descobre edital em site que ninguém mapeou.

    Nenhum teste sai para a internet: quem fala com o buscador é
    `busca.buscar_na_web`, e é sempre ele que substituímos por um dublê.
    """

    @classmethod
    def setUpTestData(cls):
        cls.consulta = ConsultaBusca.objects.create(termo='edital criança 2026')
        # Dicionário controlado — ver comentário em BuscarEditaisTests.
        PalavraChave.objects.all().delete()
        PalavraChave.objects.create(termo='criança', peso=3)
        PalavraChave.objects.create(termo='edital', peso=2)
        PalavraChave.objects.create(termo='mestrado', peso=-5)

    def test_descarta_rede_social(self):
        """Resultado de busca cai muito em rede social: é gente comentando o
        edital, não o edital."""
        from editais import busca
        crus = [
            {'title': 'Edital criança', 'href': 'https://abc.org.br/edital', 'body': ''},
            {'title': 'Edital criança', 'href': 'https://www.facebook.com/post/1', 'body': ''},
            {'title': 'Edital criança', 'href': 'https://br.pinterest.com/pin/9', 'body': ''},
        ]
        with mock.patch('ddgs.DDGS') as ddgs:
            ddgs.return_value.__enter__.return_value.text.return_value = crus
            achados = busca.buscar_na_web('qualquer coisa')

        self.assertEqual([a['link'] for a in achados], ['https://abc.org.br/edital'])

    def test_dominio_de_tira_o_www(self):
        from editais import busca
        self.assertEqual(busca.dominio_de('https://www.abc.org.br/x/y'), 'abc.org.br')
        self.assertEqual(busca.dominio_de('não é url'), '')

    def test_uma_consulta_que_falha_nao_derruba_as_outras(self):
        from editais import busca
        outra = ConsultaBusca.objects.create(termo='edital CMDCA')

        def dublê(termo, limite=20):
            if termo == 'edital criança 2026':
                raise RuntimeError('buscador bloqueou')
            return [{'titulo': 'Edital CMDCA', 'descricao': '', 'link': 'https://x.org/e'}]

        with mock.patch('editais.busca.buscar_na_web', side_effect=dublê):
            itens, erros = busca.varrer([self.consulta, outra], pausar=False)

        self.assertEqual(len(itens), 1)
        self.assertIn(self.consulta, erros)
        self.assertIn('buscador bloqueou', erros[self.consulta])

    def test_comando_grava_edital_e_marca_a_consulta(self):
        achados = [{'titulo': 'Edital para criança', 'descricao': 'projeto social',
                    'link': 'https://fundo.org.br/edital-2026'}]
        with mock.patch('editais.busca.buscar_na_web', return_value=achados):
            saida = StringIO()
            call_command('varrer_editais', '--sem-pausa', '--minimo', '2', stdout=saida)

        edital = Edital.objects.get()
        self.assertEqual(edital.origem, 'BUSCA')
        self.assertEqual(edital.consulta, self.consulta)
        self.assertGreaterEqual(edital.relevancia, 2)
        self.consulta.refresh_from_db()
        self.assertIsNotNone(self.consulta.ultima_busca)
        self.assertEqual(self.consulta.ultimo_erro, '')
        # O relatório aponta o domínio: é ele que vira fonte fixa depois.
        self.assertIn('fundo.org.br', saida.getvalue())

    def test_nao_sobrescreve_o_trabalho_do_time(self):
        """O robô roda todo dia. Se ele apagasse o que o CR escreveu, ninguém
        confiaria na lista."""
        achados = [{'titulo': 'Edital para criança', 'descricao': 'projeto social',
                    'link': 'https://fundo.org.br/edital-2026'}]
        with mock.patch('editais.busca.buscar_na_web', return_value=achados):
            call_command('varrer_editais', '--sem-pausa', stdout=StringIO())

        edital = Edital.objects.get()
        edital.status = 'INSCRITO'
        edital.observacoes = 'Livia ficou de mandar a documentação'
        edital.requisitos = 'CNPJ e 3 anos de atuação'
        edital.save()

        with mock.patch('editais.busca.buscar_na_web', return_value=achados):
            call_command('varrer_editais', '--sem-pausa', stdout=StringIO())

        self.assertEqual(Edital.objects.count(), 1)      # dedupe pelo link
        edital.refresh_from_db()
        self.assertEqual(edital.status, 'INSCRITO')
        self.assertEqual(edital.observacoes, 'Livia ficou de mandar a documentação')
        self.assertEqual(edital.requisitos, 'CNPJ e 3 anos de atuação')

    def test_dry_run_nao_grava(self):
        achados = [{'titulo': 'Edital para criança', 'descricao': '',
                    'link': 'https://fundo.org.br/edital-2026'}]
        with mock.patch('editais.busca.buscar_na_web', return_value=achados):
            call_command('varrer_editais', '--sem-pausa', '--dry-run', stdout=StringIO())

        self.assertEqual(Edital.objects.count(), 0)
        self.consulta.refresh_from_db()
        self.assertIsNone(self.consulta.ultima_busca)

    def test_palavra_negativa_barra_o_resultado(self):
        achados = [{'titulo': 'Edital de mestrado', 'descricao': 'bolsa',
                    'link': 'https://uni.br/mestrado'}]
        with mock.patch('editais.busca.buscar_na_web', return_value=achados):
            call_command('varrer_editais', '--sem-pausa', '--minimo', '2', stdout=StringIO())

        self.assertEqual(Edital.objects.count(), 0)


class PluralTests(TestCase):
    """O sufixo `(s|es)?` errava justo as palavras que mais aparecem em edital:
    o plural de '-ção' é '-ções' (normalizado '-coes'), não '-caos'. Com isso
    'doação' e 'educação' — ambas do dicionário inicial — não achavam nada, e
    editais bons ficavam abaixo da nota de corte."""

    def palavra(self, termo, peso=3):
        obj, _ = PalavraChave.objects.update_or_create(
            termo=termo, defaults={'peso': peso, 'ativo': True})
        return obj

    def test_plural_de_cao(self):
        for termo, texto in [('doação', 'edital de doacoes'),
                             ('educação', 'programa de educacoes'),
                             ('instituição', 'instituicoes sem fins lucrativos')]:
            with self.subTest(termo=termo):
                nota, _ = coleta.pontuar('', texto, [self.palavra(termo)])
                self.assertEqual(nota, 3, f'{termo!r} não achou em {texto!r}')

    def test_plural_de_palavra_terminada_em_l(self):
        nota, _ = coleta.pontuar('', 'os editais abertos', [self.palavra('edital')])
        self.assertEqual(nota, 3)

    def test_plural_de_palavra_terminada_em_m(self):
        nota, _ = coleta.pontuar('', 'os jovens do bairro', [self.palavra('jovem')])
        self.assertEqual(nota, 3)

    def test_singular_continua_achando(self):
        for termo, texto in [('doação', 'uma doação simples'),
                             ('criança', 'uma criança'),
                             ('edital', 'o edital novo')]:
            with self.subTest(termo=termo):
                nota, _ = coleta.pontuar('', texto, [self.palavra(termo)])
                self.assertEqual(nota, 3)

    def test_nao_criou_falso_positivo(self):
        """A flexão não pode custar a precisão que já existia."""
        for termo, texto in [('OSC', 'uma oscilacao grande'),
                             ('FIA', 'muita confianca'),
                             ('edital', 'editorial do jornal')]:
            with self.subTest(termo=termo):
                nota, _ = coleta.pontuar('', texto, [self.palavra(termo)])
                self.assertEqual(nota, 0, f'{termo!r} casou errado em {texto!r}')


@override_settings(TEMPLATES=TEMPLATES_DE_TESTE)
class ConsultasTelaTests(TestCase):
    """A tela das perguntas do robô.

    Ela existe porque é o que faz a varredura ser do CR e não do programador:
    ler fontes cadastradas só acha edital onde alguém já sabia procurar.
    """

    @classmethod
    def setUpTestData(cls):
        cls.cr = criar_voluntario('livia', area='CR/RE')
        cls.comum = criar_voluntario('zeca', area='RECREACAO')
        cls.consulta = ConsultaBusca.objects.create(termo='edital FIA CMDCA 2026')

    def test_cr_re_abre_e_outra_area_nao(self):
        rota = reverse('editais:consultas')
        self.assertEqual(views.consultas(requisicao('get', rota, self.cr)).status_code, 200)
        with self.assertRaises(PermissionDenied):
            views.consultas(requisicao('get', rota, self.comum))

    def test_cadastra_pergunta(self):
        rota = reverse('editais:consultas')
        views.consultas(requisicao('post', rota, self.cr,
                                   {'termo': 'edital primeira infância 2026', 'ativo': 'on'}))
        self.assertTrue(ConsultaBusca.objects.filter(
            termo='edital primeira infância 2026', ativo=True).exists())

    def test_edita_pergunta(self):
        rota = reverse('editais:consultas')
        views.consultas(requisicao('post', rota, self.cr, {
            'editar': self.consulta.pk, 'termo': 'edital FIA 2027', 'ativo': 'on'}))
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.termo, 'edital FIA 2027')

    def test_desligar_em_vez_de_apagar(self):
        """Desligar guarda a pergunta sem usá-la — o CR não perde o texto."""
        rota = reverse('editais:consultas')
        views.consultas(requisicao('post', rota, self.cr, {
            'editar': self.consulta.pk, 'termo': self.consulta.termo}))   # sem 'ativo'
        self.consulta.refresh_from_db()
        self.assertFalse(self.consulta.ativo)
        self.assertTrue(ConsultaBusca.objects.filter(pk=self.consulta.pk).exists())

    def test_apaga_pergunta_sem_apagar_os_editais_dela(self):
        """O edital já encontrado é trabalho de triagem: não pode sumir junto."""
        edital = Edital.objects.create(titulo='Edital achado', link='https://x.org/e',
                                       consulta=self.consulta, origem='BUSCA')
        views.consultas(requisicao('post', reverse('editais:consultas'), self.cr,
                                   {'excluir': self.consulta.pk}))
        self.assertFalse(ConsultaBusca.objects.filter(pk=self.consulta.pk).exists())
        edital.refresh_from_db()
        self.assertIsNone(edital.consulta)          # SET_NULL, não CASCADE

    def test_mostra_a_consulta_que_falhou(self):
        """Erro de robô tem que ser óbvio na tela, não silencioso."""
        self.consulta.ultimo_erro = 'RuntimeError: buscador bloqueou'
        self.consulta.save(update_fields=['ultimo_erro'])
        resposta = views.consultas(requisicao('get', reverse('editais:consultas'), self.cr))
        self.assertIn('com_erro=1', resposta.content.decode())


class ExtrairPrazoTests(SimpleTestCase):
    """O robô nunca preenchia `prazo`, então a regra de prazo não mordia nada.

    O extrator é melhor-esforço declarado: na dúvida devolve None e o edital
    continua aparecendo. Esconder edital vivo custa mais caro ao projeto do que
    mostrar um vencido.
    """

    HOJE = date(2026, 9, 2)

    def extrair(self, texto, titulo=''):
        from editais.prazos import extrair_prazo
        return extrair_prazo(titulo, texto, hoje=self.HOJE)

    def test_le_data_numerica_depois_do_gatilho(self):
        self.assertEqual(
            self.extrair('Inscrições até 30/11/2026 pelo site.'), date(2026, 11, 30))

    def test_le_data_escrita_em_portugues(self):
        self.assertEqual(
            self.extrair('O prazo vai até 30 de novembro de 2026.'), date(2026, 11, 30))

    def test_data_sem_gatilho_nao_e_prazo(self):
        """Edital tem data de publicação, de resultado, de início do projeto.
        Sem palavra que marque prazo, pegar a primeira data seria chute."""
        self.assertIsNone(self.extrair('Publicado em 02/09/2026 pelo instituto.'))

    def test_intervalo_fica_com_a_data_final(self):
        self.assertEqual(
            self.extrair('Inscrições de 01/10/2026 até 30/11/2026.'), date(2026, 11, 30))

    def test_ano_de_dois_digitos_ancora_no_seculo_de_hoje(self):
        self.assertEqual(self.extrair('Prazo: 30/11/26'), date(2026, 11, 30))

    def test_data_impossivel_e_descartada(self):
        self.assertIsNone(self.extrair('Inscrições até 31/02/2026.'))

    def test_data_fora_da_faixa_e_ruido_nao_prazo(self):
        self.assertIsNone(self.extrair('Entidade atuante até 30/11/1998.'))

    def test_sem_ano_assume_o_proximo_que_ainda_nao_passou(self):
        """Assumir o ano corrente venceria o edital sozinho em janeiro."""
        from editais.prazos import extrair_prazo
        self.assertEqual(
            extrair_prazo('', 'Inscrições até 30 de novembro.', hoje=date(2026, 9, 2)),
            date(2026, 11, 30))
        self.assertEqual(
            extrair_prazo('', 'Inscrições até 30 de novembro.', hoje=date(2026, 12, 15)),
            date(2027, 11, 30))

    def test_gatilho_longe_da_data_nao_conta(self):
        """Janela curta de propósito: 'inscrições' a três frases de distância
        colaria a palavra numa data que não tem nada a ver."""
        texto = ('As inscrições foram um sucesso. ' + 'Texto de enchimento. ' * 5
                 + 'O evento ocorreu em 30/11/2026.')
        self.assertIsNone(self.extrair(texto))


class PrazoUtilTests(TestCase):
    """Só aparece edital que ainda dá tempo de tentar."""

    def criar(self, titulo, dias=None, status='NOVO'):
        prazo = None if dias is None else timezone.localdate() + timedelta(days=dias)
        return Edital.objects.create(
            titulo=titulo, link=f'https://a.org/{titulo}', prazo=prazo, status=status)

    def test_prazo_com_folga_aparece(self):
        edital = self.criar('folgado', dias=30)
        self.assertIn(edital, Edital.objects.com_prazo_util())

    def test_prazo_apertado_nao_aparece(self):
        """Montar inscrição leva dias: juntar estatuto, ata, certidão, orçamento."""
        edital = self.criar('apertado', dias=5)
        self.assertNotIn(edital, Edital.objects.com_prazo_util())

    def test_prazo_vencido_nao_aparece(self):
        edital = self.criar('vencido', dias=-1)
        self.assertNotIn(edital, Edital.objects.com_prazo_util())

    def test_sem_prazo_continua_aparecendo(self):
        """A maioria do que vem de RSS não traz data. Sumir com eles esconderia
        oportunidade de verdade."""
        edital = self.criar('sem data')
        self.assertIn(edital, Edital.objects.com_prazo_util())

    def test_a_fronteira_exata_da_margem_entra(self):
        from editais.models import MARGEM_MINIMA_DIAS
        edital = self.criar('na margem', dias=MARGEM_MINIMA_DIAS)
        self.assertIn(edital, Edital.objects.com_prazo_util())

    def test_um_dia_antes_da_margem_fica_fora(self):
        from editais.models import MARGEM_MINIMA_DIAS
        edital = self.criar('quase', dias=MARGEM_MINIMA_DIAS - 1)
        self.assertNotIn(edital, Edital.objects.com_prazo_util())

    def test_o_que_o_cr_ja_decidiu_concorrer_nunca_desaparece(self):
        """Esconder edital vencido da descoberta é o objetivo; esconder aquele em
        que a pessoa já se inscreveu apagaria o pipeline dela da tela."""
        inscrito = self.criar('inscrito', dias=-10, status='INSCRITO')
        vamos = self.criar('vamos', dias=2, status='VAMOS_CONCORRER')
        visiveis = Edital.objects.com_prazo_util()
        self.assertIn(inscrito, visiveis)
        self.assertIn(vamos, visiveis)


@override_settings(TEMPLATES=TEMPLATES_DE_TESTE)
class ListaRespeitaOPrazoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.cr = criar_voluntario('livia', area='CR/RE')
        hoje = timezone.localdate()
        Edital.objects.create(titulo='Vivo', link='https://a.org/vivo',
                              prazo=hoje + timedelta(days=40), status='NOVO')
        Edital.objects.create(titulo='Vencido', link='https://a.org/velho',
                              prazo=hoje - timedelta(days=3), status='NOVO')

    def abrir(self, **filtros):
        pedido = requisicao('get', reverse('editais:lista'), self.cr, filtros)
        return views.lista(pedido).content.decode()

    def test_edital_vencido_nao_abre_na_tela(self):
        """Antes o filtro era um checkbox desligado por padrão, então a tela
        abria mostrando chamada vencida como se fosse oportunidade."""
        html = self.abrir()
        self.assertIn('[Vivo]', html)
        self.assertNotIn('[Vencido]', html)

    def test_o_contador_conta_o_mesmo_que_a_tabela_mostra(self):
        """Se os números viessem de `Edital.objects` cru, o contador diria 2 e a
        tabela mostraria 1."""
        html = self.abrir()
        self.assertIn('total=1', html)
        self.assertIn('novos=1', html)


class DicionarioSemeadoPelaMigracaoTests(TestCase):
    """As palavras-chave entram pelo deploy, não por comando que alguém lembra.

    Estes testes não criam nada: exercitam o que a migração 0002 deixou no
    banco de teste.
    """

    def test_a_migracao_deixou_termos_positivos_e_negativos(self):
        self.assertTrue(
            PalavraChave.objects.filter(termo='criança', ativo=True, peso__gt=0).exists())
        self.assertTrue(
            PalavraChave.objects.filter(termo='licitação', peso__lt=0).exists())

    def test_nenhum_termo_casa_com_palavra_comum_do_portugues(self):
        """'SUAS' (o Sistema Único de Assistência Social) foi deixado de fora de
        propósito: a pontuação casa palavra inteira sem acento, então ela
        casaria com o pronome "suas" e daria nota a edital nenhum a ver.

        O teste vale por qualquer termo curto que alguém adicione depois sem
        pensar nisso.
        """
        armadilhas = {'suas', 'seus', 'nossa', 'nossas', 'para', 'como', 'onde', 'mais'}
        termos = {coleta.normalizar(p.termo) for p in PalavraChave.objects.all()}
        self.assertEqual(termos & armadilhas, set())

    def test_termo_de_uma_letra_ou_duas_nao_entra(self):
        """Sigla de duas letras casa com preposição e artigo em qualquer texto."""
        curtos = [p.termo for p in PalavraChave.objects.all() if len(p.termo.strip()) < 3]
        self.assertEqual(curtos, [])
