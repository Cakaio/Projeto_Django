"""Chave PIX: ao vivo enquanto pendente, CONGELADA no pagamento.

A ADM pagava o reembolso perguntando a chave no grupo. Agora ela vem do perfil.

A decisao que este arquivo protege: a chave gravada no pedido e COPIA, nao
referencia — mesma razao de `ItemRetirada.pontos_unitarios` no Bazar. Se o
voluntario trocar de chave meses depois, o registro do pagamento nao pode
passar a apontar para uma chave que nao era aquela, senao o comprovante
anexado fica contradizendo a tela.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from adm import views
from adm.models import Categoria, Conta
from forms_pcf.models import PedidoReembolso

Voluntario = get_user_model()


def pedido_http(metodo, usuario, dados=None):
    fabrica = RequestFactory()
    req = (fabrica.post('/x/', dados or {}) if metodo == 'post'
           else fabrica.get('/x/'))
    req.user = usuario
    req.session = SessionStore()
    req._messages = FallbackStorage(req)
    return req


def corpo(resposta):
    return (resposta.rendered_content if hasattr(resposta, 'rendered_content')
            else resposta.content.decode())


class ChaveNoPerfilTests(TestCase):

    def test_a_chave_e_opcional(self):
        """Quem prefere receber de outro jeito nao pode ficar travado."""
        pessoa = Voluntario.objects.create_user(
            username='ana', password='x', area='AMARELO')

        pessoa.full_clean()   # nao estoura sem chave

        self.assertEqual(pessoa.chave_pix, '')

    def test_o_voluntario_edita_a_propria_chave(self):
        from voluntario.forms import MeuPerfilForm

        self.assertIn('chave_pix', MeuPerfilForm.Meta.fields)
        self.assertIn('tipo_chave_pix', MeuPerfilForm.Meta.fields)


class TelaDePagamentoTests(TestCase):

    def setUp(self):
        self.adm = Voluntario.objects.create_user(
            username='adm', password='x', area='ADM/FIN')
        self.ana = Voluntario.objects.create_user(
            username='ana', password='x', area='AMARELO',
            first_name='Ana', last_name='Souza',
            tipo_chave_pix='CELULAR', chave_pix='11987654321')
        self.categoria = Categoria.objects.create(nome='Gasolina', tipo='DESPESA')
        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.ana, valor=Decimal('50.00'), descricao='gasolina',
            data_gasto=datetime.date(2026, 9, 19), categoria=self.categoria,
            status='APROVADO')

    def _abrir(self):
        return corpo(views.reembolso_pagar(pedido_http('get', self.adm),
                                           pk=self.pedido.pk))

    def test_a_tela_mostra_a_chave_de_quem_pediu(self):
        html = self._abrir()

        self.assertIn('11987654321', html)
        self.assertIn('Ana Souza', html)
        self.assertIn('Celular', html)

    def test_sem_chave_a_tela_AVISA_em_vez_de_ficar_muda(self):
        """Sem o aviso a ADM abre a tela, nao acha a chave e volta a perguntar
        no grupo — que e o trabalho que este campo existe para tirar dela."""
        self.ana.chave_pix = ''
        self.ana.tipo_chave_pix = ''
        self.ana.save()

        html = self._abrir()

        self.assertIn('ainda não cadastrou chave PIX', html)

    def test_a_chave_le_AO_VIVO_enquanto_nao_pagou(self):
        """Se o voluntario corrigir um digito errado, a correcao vale."""
        self.ana.chave_pix = '11999998888'
        self.ana.save()

        self.assertIn('11999998888', self._abrir())


class CongelaNoPagamentoTests(TestCase):

    def setUp(self):
        self.adm = Voluntario.objects.create_user(
            username='adm', password='x', area='ADM/FIN')
        self.ana = Voluntario.objects.create_user(
            username='ana', password='x', area='AMARELO', email='ana@x.org',
            tipo_chave_pix='CELULAR', chave_pix='11987654321')
        self.categoria = Categoria.objects.create(nome='Gasolina', tipo='DESPESA')
        self.conta = Conta.objects.create(nome='BB', tipo='BANCO')
        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.ana, valor=Decimal('50.00'), descricao='gasolina',
            data_gasto=datetime.date(2026, 9, 19), categoria=self.categoria,
            status='APROVADO')

    def _pagar(self):
        # O comprovante e OBRIGATORIO no formulario: o pagamento so existe
        # com a prova anexada.
        views.reembolso_pagar(
            pedido_http('post', self.adm, {
                'conta_pagamento': self.conta.pk,
                'pago_em': '2026-09-20',
                'area': 'AMARELO',
                'comprovante_pagamento': SimpleUploadedFile(
                    'comprovante.png', b'imagem', content_type='image/png'),
            }),
            pk=self.pedido.pk)
        self.pedido.refresh_from_db()

    def test_o_pagamento_grava_a_chave_usada(self):
        self._pagar()

        self.assertEqual(self.pedido.status, 'PAGO')
        self.assertEqual(self.pedido.chave_pix_paga, '11987654321')
        self.assertEqual(self.pedido.tipo_chave_pix_paga, 'CELULAR')

    def test_trocar_de_chave_DEPOIS_nao_reescreve_o_pagamento(self):
        """O comprovante anexado ficaria contradizendo a tela."""
        self._pagar()

        self.ana.chave_pix = '22911112222'
        self.ana.save()
        self.pedido.refresh_from_db()

        self.assertEqual(self.pedido.chave_pix_paga, '11987654321')

    def test_pagar_sem_chave_cadastrada_nao_estoura(self):
        """Pagar por outro caminho continua valendo: a chave e conveniencia,
        nao requisito."""
        self.ana.chave_pix = ''
        self.ana.tipo_chave_pix = ''
        self.ana.save()

        self._pagar()

        self.assertEqual(self.pedido.status, 'PAGO')
        self.assertEqual(self.pedido.chave_pix_paga, '')


class ChaveNaCaixaDeEntradaTests(TestCase):
    """A chave aparece na caixa de entrada, em coluna propria e clicavel.

    A primeira versao PROIBIA isso, com teste: "dado pessoal so serve na hora
    de pagar". A regra foi desfeita a pedido, e a evidencia dava razao ao
    pedido: `REEMBOLSO_AREAS` e {'ADM/FIN'}, o MESMO publico da tela de pagar.
    Nao havia exposicao nova — so o trabalho de abrir pedido por pedido para
    copiar a chave.
    """

    def setUp(self):
        self.adm = Voluntario.objects.create_user(
            username='adm', password='x', area='ADM/FIN')
        self.ana = Voluntario.objects.create_user(
            username='ana', password='x', area='AMARELO',
            first_name='Ana', last_name='Souza',
            tipo_chave_pix='CELULAR', chave_pix='11987654321')
        self.categoria = Categoria.objects.create(nome='Gasolina',
                                                  tipo='DESPESA')
        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.ana, valor=Decimal('50.00'), descricao='gasolina',
            data_gasto=datetime.date(2026, 9, 19), categoria=self.categoria)

    def _html(self, usuario=None):
        from forms_pcf import views as forms_views

        return corpo(forms_views.ReembolsoInboxView.as_view()(
            pedido_http('get', usuario or self.adm)))

    def test_a_chave_aparece_na_coluna(self):
        html = self._html()

        self.assertIn('11987654321', html)
        self.assertIn('>PIX<', html)

    def test_a_chave_e_clicavel_para_copiar(self):
        """`<button>` e nao `<span>` com onclick: so o botao e alcancavel por
        teclado e anunciado como acionavel por leitor de tela."""
        html = self._html()

        self.assertIn('data-pix="11987654321"', html)
        self.assertIn('class="rmb-pix"', html)

    def test_sem_chave_a_coluna_diz_sem_chave(self):
        """Celula vazia faria a ADM achar que a tela nao carregou o dado."""
        self.ana.chave_pix = ''
        self.ana.tipo_chave_pix = ''
        self.ana.save()

        html = self._html()

        self.assertIn('sem chave', html)
        self.assertNotIn('data-pix="11987654321"', html)

    def test_a_caixa_continua_sendo_so_de_ADM_FIN(self):
        """E o que torna a coluna aceitavel: o publico da lista e o MESMO da
        tela de pagar. Se este gate afrouxar, a coluna vira exposicao."""
        from django.core.exceptions import PermissionDenied
        from forms_pcf import views as forms_views

        for area in ('AMARELO', 'SUPPLY', 'TRIADE'):
            de_fora = Voluntario.objects.create_user(
                username=f'u{area}', password='x', area=area)
            with self.assertRaises(PermissionDenied, msg=area):
                forms_views.ReembolsoInboxView.as_view()(
                    pedido_http('get', de_fora))

    def test_a_copia_tem_volta_quando_o_navegador_recusa(self):
        """`navigator.clipboard` exige HTTPS e nao existe em navegador antigo.
        Sem a volta, a ADM clica e NADA acontece — e conclui que travou."""
        html = self._html()

        self.assertIn('Copie a chave PIX', html)


class TabelaDaCaixaDeEntradaTests(TestCase):
    """A tabela tem de continuar inteira quando ganha coluna.

    Acrescentar a coluna do PIX quebrou DUAS coisas de uma vez, e nenhuma
    dava erro: o `colspan` da linha "nenhum pedido" ficou um a menos que as
    colunas, e os selects de area/evento colapsaram para uma fresta porque a
    tabela nao tinha largura para oito colunas.
    """

    def setUp(self):
        self.adm = Voluntario.objects.create_user(
            username='adm', password='x', area='ADM/FIN')

    def _html(self):
        from forms_pcf import views as forms_views

        return corpo(forms_views.ReembolsoInboxView.as_view()(
            pedido_http('get', self.adm)))

    def test_o_colspan_da_linha_vazia_bate_com_as_colunas(self):
        """Um a menos e a tabela sai torta, sem erro nenhum."""
        import re

        html = self._html()
        cabecalho = html[html.index('<thead'):html.index('</thead>')]
        colunas = len(re.findall(r'<th[\s>]', cabecalho))

        colspans = [int(n) for n in re.findall(r'colspan="(\d+)"', html)]

        self.assertTrue(colspans, 'A linha de "nenhum pedido" sumiu.')
        for valor in colspans:
            self.assertEqual(
                valor, colunas,
                f'colspan={valor} com {colunas} colunas: a tabela sai torta.')

    def test_o_select_de_area_nao_pode_colapsar(self):
        """Com o rotulo AO LADO, ele era `nowrap` e ficava com todo o espaco;
        o select encolhia ate virar uma fresta com barra de rolagem dentro."""
        html = self._html()

        self.assertIn('min-width: 9rem', html)
        # A grade de duas colunas era o que permitia o colapso.
        self.assertNotIn('grid-template-columns: auto minmax(0, 1fr)', html)
