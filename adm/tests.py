import tempfile

from django.test import TestCase, RequestFactory, Client, override_settings
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from django.template import TemplateDoesNotExist
from django.urls import reverse
from unittest.mock import MagicMock, patch
from datetime import date
from decimal import Decimal
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from adm.models import Categoria, Conta, Evento, Lancamento, RecargaCartao, TetoArea
from adm.servicos import (
    SEM_AREA, SEM_CATEGORIA, _linha_despesa, despesas_por_categoria,
    gasto_por_area, saldo_das_contas, situacao_dos_tetos,
)
from adm.views import (
    AdmAcessoMixin, AdmEscritaMixin, _periodo_prestacao_contas, _semestre_escolhido,
    completar_lancamento,
    contas as view_contas, onde_investimos, recargas as view_recargas,
    reembolso_pagar, tetos as view_tetos,
)
from forms_pcf.forms import PagamentoReembolsoForm
from forms_pcf.models import ReceptorNotificacaoReembolso, PedidoReembolso
from forms_pcf.views import sincronizar_lancamento_do_reembolso

User = get_user_model()


class CategoriaModelTest(TestCase):
    def test_str(self):
        cat = Categoria(nome='Doação', tipo='RECEITA')
        self.assertEqual(str(cat), 'Doação (Receita)')


class LancamentoModelTest(TestCase):
    def setUp(self):
        self.cat_receita = Categoria.objects.create(nome='Doação', tipo='RECEITA')
        self.cat_despesa = Categoria.objects.create(nome='Materiais', tipo='DESPESA')

    def test_tipo_derivado_da_categoria(self):
        """tipo deve ser preenchido automaticamente a partir da categoria"""
        lan = Lancamento.objects.create(
            categoria=self.cat_receita,
            valor='100.00',
            data=timezone.now().date(),
        )
        self.assertEqual(lan.tipo, 'RECEITA')

    def test_tipo_despesa_derivado(self):
        lan = Lancamento.objects.create(
            categoria=self.cat_despesa,
            valor='50.00',
            data=timezone.now().date(),
        )
        self.assertEqual(lan.tipo, 'DESPESA')


class MixinTest(TestCase):
    def _make_user(self, area, superuser=False):
        u = MagicMock()
        u.is_authenticated = True
        u.is_superuser = superuser
        u.area = area
        return u

    def _make_request(self, area, superuser=False):
        req = MagicMock()
        req.user = self._make_user(area, superuser)
        return req

    def test_adm_fin_tem_acesso_leitura(self):
        """ADM/FIN deve passar pela verificação de acesso sem PermissionDenied."""
        mixin = AdmAcessoMixin()
        mixin.handle_no_permission = MagicMock()
        req = self._make_request('ADM/FIN')
        raised = False
        try:
            with patch('adm.views.super') as mock_super:
                mock_super.return_value.dispatch = MagicMock(return_value=None)
                mixin.dispatch(req)
        except PermissionDenied:
            raised = True
        self.assertFalse(raised, "ADM/FIN não deve receber PermissionDenied")

    def test_voluntario_sem_area_bloqueado(self):
        """Voluntário de área não autorizada deve receber PermissionDenied."""
        mixin = AdmAcessoMixin()
        mixin.handle_no_permission = MagicMock()
        req = self._make_request('AZUL')
        with self.assertRaises(PermissionDenied):
            mixin.dispatch(req)


class CategoriaViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_adm = User.objects.create_user(
            username='adm_user', password='pass', area='ADM/FIN',
            first_name='ADM', last_name='User'
        )
        self.user_outro = User.objects.create_user(
            username='outro', password='pass', area='AZUL',
            first_name='Outro', last_name='User'
        )

    def test_lista_requer_login(self):
        resp = self.client.get('/adm/categorias/')
        self.assertEqual(resp.status_code, 302)

    def test_outro_bloqueado(self):
        self.client.login(username='outro', password='pass')
        resp = self.client.get('/adm/categorias/')
        self.assertEqual(resp.status_code, 403)

    def test_criar_categoria(self):
        self.client.login(username='adm_user', password='pass')
        resp = self.client.post('/adm/categorias/nova/', {
            'nome': 'Doação', 'tipo': 'RECEITA', 'ativo': True
        }, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Categoria.objects.filter(nome='Doação').exists())


class LancamentoViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_adm = User.objects.create_user(
            username='adm2', password='pass', area='ADM/FIN',
            first_name='ADM', last_name='Dois'
        )
        self.cat = Categoria.objects.create(nome='Doação', tipo='RECEITA')

    def test_criar_lancamento_manual(self):
        self.client.login(username='adm2', password='pass')
        resp = self.client.post('/adm/lancamentos/novo/', {
            'categoria': self.cat.pk,
            'valor': '500.00',
            'data': timezone.now().date().isoformat(),
            'descricao': 'Doação teste',
        }, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/adm/lancamentos/')
        self.assertTrue(Lancamento.objects.filter(descricao='Doação teste').exists())

    def test_nao_edita_lancamento_supply(self):
        lan = Lancamento.objects.create(
            categoria=self.cat, valor='100', data=timezone.now().date(), origem='SUPPLY'
        )
        self.client.login(username='adm2', password='pass')
        resp = self.client.get(f'/adm/lancamentos/{lan.pk}/editar/', follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/adm/lancamentos/')


class FluxoCaixaTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_adm = User.objects.create_user(
            username='adm_fc', password='pass', area='ADM/FIN',
            first_name='ADM', last_name='FC'
        )
        self.cat_r = Categoria.objects.create(nome='Doação FC', tipo='RECEITA')
        self.cat_d = Categoria.objects.create(nome='Fixo FC', tipo='DESPESA')
        hoje = timezone.now().date()
        Lancamento.objects.create(categoria=self.cat_r, valor='1000', data=hoje)
        Lancamento.objects.create(categoria=self.cat_d, valor='300', data=hoje)

    def test_saldo_calculado(self):
        self.client.login(username='adm_fc', password='pass')
        resp = self.client.get('/adm/fluxo-de-caixa/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '700')  # saldo 1000 - 300

    def test_exportar_csv(self):
        self.client.login(username='adm_fc', password='pass')
        resp = self.client.get('/adm/fluxo-de-caixa/?exportar=csv')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])


class SupplySignalTest(TestCase):
    def setUp(self):
        # Criar a categoria padrão que o signal usa
        self.cat_supply = Categoria.objects.create(
            nome='Materiais Supply', tipo='DESPESA', ativo=True
        )
        # Criar Sabado e Pedido via ORM direto
        from sabado.models import Sabado
        from supply.models import Pedido

        self.user = User.objects.create_user(
            username='sup_user', password='pass', area='SUPPLY',
            first_name='Sup', last_name='User'
        )
        self.sabado = Sabado.objects.create(
            data=timezone.now().date(), tema='Teste', descricao='Teste'
        )
        self.Pedido = Pedido

    def test_pedido_com_valor_cria_lancamento(self):
        pedido = self.Pedido.objects.create(
            nome='Tinta azul', quantidade=2, valor='45.00',
            sabado=self.sabado, area='SUPPLY'
        )
        self.assertTrue(Lancamento.objects.filter(pedido=pedido).exists())
        lan = Lancamento.objects.get(pedido=pedido)
        self.assertEqual(lan.valor, Decimal('45.00'))
        self.assertEqual(lan.origem, 'SUPPLY')

    def test_pedido_sem_valor_nao_cria_lancamento(self):
        pedido = self.Pedido.objects.create(
            nome='Tinta sem valor', quantidade=1,
            sabado=self.sabado, area='SUPPLY'
        )
        self.assertFalse(Lancamento.objects.filter(pedido=pedido).exists())

    def test_deletar_pedido_remove_lancamento(self):
        pedido = self.Pedido.objects.create(
            nome='Item para deletar', quantidade=1, valor='10.00',
            sabado=self.sabado, area='SUPPLY'
        )
        pk = pedido.pk
        pedido.delete()
        self.assertFalse(Lancamento.objects.filter(pedido_id=pk).exists())


class DRETest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_adm = User.objects.create_user(
            username='adm_dre', password='pass', area='ADM/FIN',
            first_name='ADM', last_name='DRE'
        )
        self.cat_r = Categoria.objects.create(nome='Doação DRE', tipo='RECEITA')
        self.cat_d = Categoria.objects.create(nome='Fixo DRE', tipo='DESPESA')
        import datetime
        self.hoje = datetime.date(2026, 1, 15)
        Lancamento.objects.create(categoria=self.cat_r, valor='2000', data=self.hoje)
        Lancamento.objects.create(categoria=self.cat_d, valor='500', data=self.hoje)

    def test_dre_resultado_correto(self):
        self.client.login(username='adm_dre', password='pass')
        resp = self.client.get('/adm/dre/?mes=2026-01')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '1500')  # resultado 2000-500

    def test_dre_comparativo(self):
        self.client.login(username='adm_dre', password='pass')
        resp = self.client.get('/adm/dre/?mes=2026-01&comparar=2025-12')
        self.assertEqual(resp.status_code, 200)


class PainelTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_triade = User.objects.create_user(
            username='triade_user', password='pass', area='TRIADE',
            first_name='Triade', last_name='User'
        )

    def test_triade_acessa_painel(self):
        self.client.login(username='triade_user', password='pass')
        resp = self.client.get('/adm/')
        self.assertEqual(resp.status_code, 200)

    def test_painel_sem_login_redireciona(self):
        resp = self.client.get('/adm/')
        self.assertEqual(resp.status_code, 302)


class ReceptoresReembolsoViewTest(TestCase):
    def _adm_client(self):
        c = Client()
        u = User.objects.create_user(username='adm_r', password='pw', area='ADM/FIN')
        c.force_login(u)
        return c, u

    def test_lista_acessivel_por_adm(self):
        c, _ = self._adm_client()
        resp = c.get(reverse('adm:receptores_reembolso'))
        self.assertEqual(resp.status_code, 200)

    def test_criar_receptor(self):
        c, _ = self._adm_client()
        resp = c.post(reverse('adm:receptor_criar'), {
            'nome': 'Financeiro PCF',
            'email': 'fin@pcf.org',
            'ativo': True,
        })
        self.assertRedirects(resp, reverse('adm:receptores_reembolso'))
        self.assertEqual(ReceptorNotificacaoReembolso.objects.count(), 1)

    def test_outro_area_recebe_403(self):
        c = Client()
        u = User.objects.create_user(username='mkt_r', password='pw', area='MARKETING')
        c.force_login(u)
        resp = c.get(reverse('adm:receptores_reembolso'))
        self.assertEqual(resp.status_code, 403)


class PainelReembolsoBadgeTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.adm = User.objects.create_user(username='adm_badge', password='pw', area='ADM/FIN')
        self.client.force_login(self.adm)
        cat = Categoria.objects.create(nome='Geral', tipo='DESPESA')
        PedidoReembolso.objects.create(
            solicitante=self.adm, valor='10.00',
            descricao='x', data_gasto=timezone.now().date(),
            categoria=cat, comprovante='reembolsos/x.jpg', status='PENDENTE'
        )

    def test_painel_contem_contagem_pendente(self):
        resp = self.client.get(reverse('adm:painel'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('reembolsos_pendentes', resp.context)
        self.assertEqual(resp.context['reembolsos_pendentes'], 1)


class DespesasPorCategoriaTest(TestCase):
    """O número que o CR leva ao doador. Se ele estiver errado, a prestação de
    contas mente — por isso o cálculo é testado contra o banco, não simulado."""

    def setUp(self):
        self.alimentacao = Categoria.objects.create(nome='Alimentação', tipo='DESPESA')
        self.transporte = Categoria.objects.create(nome='Transporte', tipo='DESPESA')
        self.doacao = Categoria.objects.create(nome='Doação', tipo='RECEITA')

        self.inicio = date(2026, 1, 1)
        self.fim = date(2026, 12, 31)

        Lancamento.objects.create(categoria=self.alimentacao, valor='300.00', data=date(2026, 3, 10))
        Lancamento.objects.create(categoria=self.alimentacao, valor='100.00', data=date(2026, 4, 20))
        Lancamento.objects.create(categoria=self.transporte, valor='100.00', data=date(2026, 5, 5))
        # Receita e despesa de outro ano existem só para provar que ficam fora.
        Lancamento.objects.create(categoria=self.doacao, valor='9000.00', data=date(2026, 2, 1))
        Lancamento.objects.create(categoria=self.transporte, valor='777.00', data=date(2025, 8, 1))

    def test_agrupa_soma_e_conta_por_categoria(self):
        linhas, total = despesas_por_categoria(self.inicio, self.fim)

        self.assertEqual(total, Decimal('500.00'))
        self.assertEqual(len(linhas), 2)
        self.assertEqual(linhas[0]['nome'], 'Alimentação')
        self.assertEqual(linhas[0]['valor'], Decimal('400.00'))
        self.assertEqual(linhas[0]['lancamentos'], 2)
        self.assertEqual(linhas[1]['nome'], 'Transporte')
        self.assertEqual(linhas[1]['valor'], Decimal('100.00'))
        self.assertEqual(linhas[1]['lancamentos'], 1)

    def test_ordena_do_maior_gasto_para_o_menor(self):
        linhas, _ = despesas_por_categoria(self.inicio, self.fim)
        self.assertEqual([linha['nome'] for linha in linhas], ['Alimentação', 'Transporte'])

    def test_percentual_com_uma_casa(self):
        linhas, _ = despesas_por_categoria(self.inicio, self.fim)
        self.assertEqual(linhas[0]['percentual'], Decimal('80.0'))
        self.assertEqual(linhas[1]['percentual'], Decimal('20.0'))

    def test_receita_e_periodo_de_fora_nao_entram(self):
        _, total = despesas_por_categoria(self.inicio, self.fim)
        # 9000 de receita + 777 de 2025 entrariam se o filtro estivesse frouxo.
        self.assertEqual(total, Decimal('500.00'))

    def test_periodo_sem_despesa_devolve_vazio(self):
        linhas, total = despesas_por_categoria(date(2020, 1, 1), date(2020, 12, 31))
        self.assertEqual(linhas, [])
        self.assertEqual(total, Decimal('0'))

    def test_uma_consulta_so(self):
        """O contrato pede agregação em uma consulta: laço com query dentro
        derrubaria a tela quando o histórico crescer."""
        with self.assertNumQueries(1):
            despesas_por_categoria(self.inicio, self.fim)


class DespesaTotalZeroTest(TestCase):
    """Total zero com linha existindo é o caso que dividiria por zero."""

    def test_lancamento_de_valor_zero_nao_divide_por_zero(self):
        categoria = Categoria.objects.create(nome='Doado em espécie', tipo='DESPESA')
        Lancamento.objects.create(categoria=categoria, valor='0.00', data=date(2026, 6, 1))

        linhas, total = despesas_por_categoria(date(2026, 1, 1), date(2026, 12, 31))

        self.assertEqual(total, Decimal('0.00'))
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]['percentual'], Decimal('0.0'))

    def test_linha_isolada_com_total_zero(self):
        linha = _linha_despesa(
            {'categoria__nome': 'Qualquer', 'valor_total': Decimal('0'), 'quantidade': 1},
            Decimal('0'),
        )
        self.assertEqual(linha['percentual'], Decimal('0.0'))


class CategoriaNulaTest(TestCase):
    """Lancamento.categoria é NOT NULL no banco, então a categoria nula só
    aparece se o schema mudar. O teste vai direto na montagem da linha porque é
    lá que mora a defesa — e ela precisa continuar de pé."""

    def test_categoria_nula_vira_sem_categoria(self):
        linha = _linha_despesa(
            {'categoria__nome': None, 'valor_total': Decimal('50.00'), 'quantidade': 2},
            Decimal('100.00'),
        )
        self.assertEqual(linha['nome'], SEM_CATEGORIA)
        self.assertEqual(linha['nome'], 'Sem categoria')
        self.assertEqual(linha['percentual'], Decimal('50.0'))


class OndeInvestimosAcessoTest(TestCase):
    """Este gate é mais largo que o resto do Financeiro: o CR/RE entra aqui e
    em nenhuma outra tela do adm."""

    def setUp(self):
        self.fabrica = RequestFactory()

    def _gate_liberou(self, usuario):
        """True se a view deixou o usuário passar.

        RequestFactory em vez do test Client porque o Client quebra ao copiar o
        contexto do template neste ambiente (Python 3.14). O template é entrega
        de outro agente, então TemplateDoesNotExist também conta como liberado:
        o que se prova aqui é a permissão, não o HTML.
        """
        requisicao = self.fabrica.get('/adm/onde-investimos/')
        requisicao.user = usuario
        try:
            onde_investimos(requisicao)
        except PermissionDenied:
            return False
        except TemplateDoesNotExist:
            return True
        return True

    def _voluntario(self, username, area, superuser=False):
        return User.objects.create_user(
            username=username, password='pw', area=area, is_superuser=superuser
        )

    def test_crre_entra(self):
        self.assertTrue(self._gate_liberou(self._voluntario('cr_oi', 'CR/RE')))

    def test_adm_fin_entra(self):
        self.assertTrue(self._gate_liberou(self._voluntario('fin_oi', 'ADM/FIN')))

    def test_triade_entra(self):
        self.assertTrue(self._gate_liberou(self._voluntario('tri_oi', 'TRIADE')))

    def test_area_sem_poder_toma_403(self):
        usuario = self._voluntario('mkt_oi', 'MARKETING')
        self.assertFalse(self._gate_liberou(usuario))

    def test_area_sem_poder_responde_403_pela_url(self):
        """Pelo Client mesmo: PermissionDenied só serve se virar 403 de fato.
        Aqui o Client funciona porque a resposta de erro não renderiza o
        template da tela."""
        cliente = Client()
        cliente.force_login(self._voluntario('mkt_url', 'MARKETING'))
        self.assertEqual(cliente.get('/adm/onde-investimos/').status_code, 403)

    def test_superuser_entra_mesmo_sem_area_de_poder(self):
        """Área MARKETING de propósito: prova que quem abriu a porta foi o
        is_superuser, e não a área."""
        usuario = self._voluntario('root_oi', 'MARKETING', superuser=True)
        self.assertTrue(self._gate_liberou(usuario))

    def test_sem_login_redireciona(self):
        resposta = Client().get('/adm/onde-investimos/')
        self.assertEqual(resposta.status_code, 302)

    def test_rota_registrada(self):
        self.assertEqual(reverse('adm:onde_investimos'), '/adm/onde-investimos/')


class PeriodoOndeInvestimosTest(TestCase):
    """Filtro colado torto no WhatsApp não pode virar erro 500."""

    def setUp(self):
        self.fabrica = RequestFactory()
        hoje = timezone.localdate()
        self.padrao = (date(hoje.year, 1, 1), date(hoje.year, 12, 31))

    def _periodo(self, querystring=''):
        return _periodo_prestacao_contas(
            self.fabrica.get('/adm/onde-investimos/' + querystring)
        )

    def test_padrao_e_o_ano_corrente(self):
        self.assertEqual(self._periodo(), self.padrao)

    def test_periodo_valido_e_respeitado(self):
        self.assertEqual(
            self._periodo('?inicio=2026-03-01&fim=2026-03-31'),
            (date(2026, 3, 1), date(2026, 3, 31)),
        )

    def test_data_com_dia_inexistente_cai_no_padrao(self):
        # parse_date() levanta ValueError aqui, não devolve None.
        self.assertEqual(self._periodo('?inicio=2026-02-31&fim=2026-12-31'), self.padrao)

    def test_texto_qualquer_cai_no_padrao(self):
        self.assertEqual(self._periodo('?inicio=ontem&fim=amanha'), self.padrao)

    def test_periodo_invertido_cai_no_padrao(self):
        self.assertEqual(self._periodo('?inicio=2026-12-31&fim=2026-01-01'), self.padrao)

    def test_view_nao_estoura_com_filtro_invalido(self):
        """Ponta a ponta: gate + período + serviço, sem 500 no caminho."""
        requisicao = self.fabrica.get('/adm/onde-investimos/?inicio=xx&fim=2026-02-31')
        requisicao.user = User.objects.create_user(
            username='cr_filtro', password='pw', area='CR/RE'
        )
        try:
            onde_investimos(requisicao)
        except TemplateDoesNotExist:
            pass  # Chegou até a renderização: o cálculo passou inteiro.


# ─── Contas, cartões e saldo ───

class SaldoDoCartaoTest(TestCase):
    """O saldo do cartão é recarga MENOS gasto. Se a recarga virasse lançamento,
    o mesmo real seria contado duas vezes: uma na recarga, outra no uso."""

    def setUp(self):
        self.cartao = Conta.objects.create(
            nome='Caju Recreação', tipo='CARTAO', controla_saldo=True
        )
        self.despesa = Categoria.objects.create(nome='Materiais', tipo='DESPESA')
        self.receita = Categoria.objects.create(nome='Doação', tipo='RECEITA')

    def test_recarga_nao_gera_lancamento(self):
        RecargaCartao.objects.create(
            conta=self.cartao, data=date(2026, 8, 1), valor='300.00'
        )
        # Zero lançamentos: recarga é dinheiro mudando de bolso, não gasto.
        self.assertEqual(Lancamento.objects.count(), 0)
        self.assertEqual(self.cartao.saldo, Decimal('300.00'))

    def test_saldo_e_recarga_menos_gasto(self):
        RecargaCartao.objects.create(conta=self.cartao, data=date(2026, 8, 1), valor='300.00')
        RecargaCartao.objects.create(conta=self.cartao, data=date(2026, 8, 10), valor='200.00')
        Lancamento.objects.create(
            categoria=self.despesa, valor='120.00', data=date(2026, 8, 12), conta=self.cartao
        )
        self.assertEqual(self.cartao.total_recarregado, Decimal('500.00'))
        self.assertEqual(self.cartao.total_gasto, Decimal('120.00'))
        self.assertEqual(self.cartao.saldo, Decimal('380.00'))
        self.assertFalse(self.cartao.saldo_negativo)

    def test_receita_na_conta_nao_consome_saldo(self):
        RecargaCartao.objects.create(conta=self.cartao, data=date(2026, 8, 1), valor='100.00')
        Lancamento.objects.create(
            categoria=self.receita, valor='900.00', data=date(2026, 8, 3), conta=self.cartao
        )
        # Receita entrando na conta não é gasto: subtrair inverteria o sinal.
        self.assertEqual(self.cartao.total_gasto, Decimal('0'))
        self.assertEqual(self.cartao.saldo, Decimal('100.00'))

    def test_conta_sem_movimento_devolve_zero_e_nao_none(self):
        # A tela formata como dinheiro: None viraria "R$ None".
        self.assertEqual(self.cartao.total_recarregado, Decimal('0'))
        self.assertEqual(self.cartao.total_gasto, Decimal('0'))
        self.assertEqual(self.cartao.saldo, Decimal('0'))

    def test_gasto_maior_que_recarga_acusa_saldo_negativo(self):
        RecargaCartao.objects.create(conta=self.cartao, data=date(2026, 8, 1), valor='50.00')
        Lancamento.objects.create(
            categoria=self.despesa, valor='80.00', data=date(2026, 8, 2), conta=self.cartao
        )
        self.assertEqual(self.cartao.saldo, Decimal('-30.00'))
        self.assertTrue(self.cartao.saldo_negativo)

    def test_gasto_de_outra_conta_nao_entra(self):
        outro = Conta.objects.create(nome='BB', tipo='BANCO')
        RecargaCartao.objects.create(conta=self.cartao, data=date(2026, 8, 1), valor='100.00')
        Lancamento.objects.create(
            categoria=self.despesa, valor='70.00', data=date(2026, 8, 2), conta=outro
        )
        self.assertEqual(self.cartao.saldo, Decimal('100.00'))


class SaldoDasContasTest(TestCase):
    def setUp(self):
        self.cartao = Conta.objects.create(nome='Caju', tipo='CARTAO', controla_saldo=True)
        self.banco = Conta.objects.create(nome='BB', tipo='BANCO', controla_saldo=False)
        self.despesa = Categoria.objects.create(nome='Materiais', tipo='DESPESA')
        RecargaCartao.objects.create(conta=self.cartao, data=date(2026, 8, 1), valor='400.00')
        Lancamento.objects.create(
            categoria=self.despesa, valor='150.00', data=date(2026, 8, 5), conta=self.cartao
        )
        Lancamento.objects.create(
            categoria=self.despesa, valor='999.00', data=date(2026, 8, 5), conta=self.banco
        )

    def test_lista_so_quem_controla_saldo(self):
        linhas = saldo_das_contas()
        self.assertEqual([linha['conta'].nome for linha in linhas], ['Caju'])

    def test_valores_da_linha(self):
        linha = saldo_das_contas()[0]
        self.assertEqual(linha['recarregado'], Decimal('400.00'))
        self.assertEqual(linha['gasto'], Decimal('150.00'))
        self.assertEqual(linha['saldo'], Decimal('250.00'))
        self.assertFalse(linha['negativo'])

    def test_numero_fixo_de_consultas(self):
        """Três consultas, sempre: com query dentro do laço a tela ficaria mais
        lenta a cada cartão novo."""
        Conta.objects.create(nome='Mercado Pago', tipo='CARTAO', controla_saldo=True)
        Conta.objects.create(nome='Caju Supply', tipo='CARTAO', controla_saldo=True)
        with self.assertNumQueries(3):
            saldo_das_contas()

    def test_sem_conta_controlada_devolve_vazio(self):
        Conta.objects.filter(controla_saldo=True).update(controla_saldo=False)
        self.assertEqual(saldo_das_contas(), [])


# ─── Tetos por área ───

class SituacaoDosTetosTest(TestCase):
    def setUp(self):
        self.despesa = Categoria.objects.create(nome='Materiais', tipo='DESPESA')
        self.receita = Categoria.objects.create(nome='Doação', tipo='RECEITA')
        # Referência dentro do 2º semestre de 2026 (jul–dez).
        self.referencia = date(2026, 8, 1)

    def _gasto(self, area, valor, dia=10):
        return Lancamento.objects.create(
            categoria=self.despesa, valor=valor, data=date(2026, 8, dia), area=area
        )

    def _linha(self, linhas, area):
        return next(linha for linha in linhas if linha['area'] == area)

    def test_area_com_teto_e_gasto(self):
        TetoArea.objects.create(area='SUPPLY', valor='1000.00')
        self._gasto('SUPPLY', '250.00')

        linha = self._linha(situacao_dos_tetos(self.referencia), 'SUPPLY')
        self.assertEqual(linha['teto'], Decimal('1000.00'))
        self.assertEqual(linha['gasto'], Decimal('250.00'))
        self.assertEqual(linha['disponivel'], Decimal('750.00'))
        self.assertEqual(linha['percentual'], Decimal('25.0'))
        self.assertFalse(linha['estourou'])
        self.assertFalse(linha['sem_teto'])
        self.assertEqual(linha['nome'], 'Supply')

    def test_area_com_teto_e_sem_gasto_aparece_zerada(self):
        TetoArea.objects.create(area='RECREACAO', valor='500.00')
        linha = self._linha(situacao_dos_tetos(self.referencia), 'RECREACAO')
        self.assertEqual(linha['gasto'], Decimal('0'))
        self.assertEqual(linha['disponivel'], Decimal('500.00'))
        self.assertEqual(linha['percentual'], Decimal('0.0'))

    def test_gasto_sem_teto_aparece_e_e_denunciado(self):
        """É o furo que a tela existe para mostrar: esconder deixaria invisível."""
        self._gasto('VIOLETA', '80.00')

        linha = self._linha(situacao_dos_tetos(self.referencia), 'VIOLETA')
        self.assertTrue(linha['sem_teto'])
        self.assertIsNone(linha['teto'])
        self.assertEqual(linha['gasto'], Decimal('80.00'))
        self.assertEqual(linha['percentual'], Decimal('0.0'))

    def test_teto_zero_com_gasto_nao_divide_por_zero(self):
        TetoArea.objects.create(area='EVENTOS', valor='0.00')
        self._gasto('EVENTOS', '40.00')

        linha = self._linha(situacao_dos_tetos(self.referencia), 'EVENTOS')
        self.assertEqual(linha['teto'], Decimal('0.00'))
        self.assertTrue(linha['estourou'])
        self.assertEqual(linha['percentual'], Decimal('100.0'))
        self.assertEqual(linha['disponivel'], Decimal('-40.00'))

    def test_teto_zero_sem_gasto_nao_divide_por_zero(self):
        TetoArea.objects.create(area='MARKETING', valor='0.00')
        linha = self._linha(situacao_dos_tetos(self.referencia), 'MARKETING')
        self.assertFalse(linha['estourou'])
        self.assertEqual(linha['percentual'], Decimal('0.0'))

    def test_estouro_de_teto(self):
        TetoArea.objects.create(area='SUPPLY', valor='100.00')
        self._gasto('SUPPLY', '150.00')

        linha = self._linha(situacao_dos_tetos(self.referencia), 'SUPPLY')
        self.assertTrue(linha['estourou'])
        self.assertEqual(linha['percentual'], Decimal('150.0'))
        self.assertEqual(linha['disponivel'], Decimal('-50.00'))

    def test_estouro_vem_primeiro_e_sem_teto_depois(self):
        TetoArea.objects.create(area='SUPPLY', valor='100.00')
        TetoArea.objects.create(area='RECREACAO', valor='500.00')
        self._gasto('SUPPLY', '150.00')      # estourou
        self._gasto('VIOLETA', '10.00')      # gastou sem teto
        self._gasto('RECREACAO', '50.00')    # dentro do teto

        ordem = [linha['area'] for linha in situacao_dos_tetos(self.referencia)]
        self.assertEqual(ordem[:2], ['SUPPLY', 'VIOLETA'])

    def test_receita_nao_conta_como_gasto(self):
        TetoArea.objects.create(area='SUPPLY', valor='100.00')
        Lancamento.objects.create(
            categoria=self.receita, valor='5000.00', data=date(2026, 8, 5), area='SUPPLY'
        )
        linha = self._linha(situacao_dos_tetos(self.referencia), 'SUPPLY')
        self.assertEqual(linha['gasto'], Decimal('0'))

    def test_despesa_sem_area_nao_cria_linha(self):
        self._gasto('', '70.00')
        # Sem área não pertence a teto de ninguém: viraria acusação a uma área
        # que não existe.
        self.assertEqual(situacao_dos_tetos(self.referencia), [])

    def test_qualquer_data_do_semestre_da_o_mesmo_recorte(self):
        """A referência é só para achar o semestre; o dia não recorta nada."""
        TetoArea.objects.create(area='SUPPLY', valor='100.00')
        self._gasto('SUPPLY', '30.00', dia=20)
        for referencia in (date(2026, 7, 1), date(2026, 8, 17), date(2026, 12, 31)):
            with self.subTest(referencia=referencia):
                linha = self._linha(situacao_dos_tetos(referencia), 'SUPPLY')
                self.assertEqual(linha['gasto'], Decimal('30.00'))

    def test_gasto_do_outro_semestre_fica_fora(self):
        """O teto é por semestre: gasto de janeiro não pesa no segundo."""
        TetoArea.objects.create(area='SUPPLY', valor='100.00')
        Lancamento.objects.create(categoria=self.despesa, valor='40.00',
                                  data=date(2026, 3, 10), area='SUPPLY')   # 1º semestre
        self._gasto('SUPPLY', '30.00')                                      # 2º semestre
        self.assertEqual(self._linha(situacao_dos_tetos(date(2026, 8, 1)), 'SUPPLY')['gasto'],
                         Decimal('30.00'))
        self.assertEqual(self._linha(situacao_dos_tetos(date(2026, 3, 1)), 'SUPPLY')['gasto'],
                         Decimal('40.00'))

    def test_as_duas_pontas_do_semestre_entram(self):
        TetoArea.objects.create(area='SUPPLY', valor='1000.00')
        for dia in (date(2026, 7, 1), date(2026, 12, 31)):
            Lancamento.objects.create(categoria=self.despesa, valor='10.00',
                                      data=dia, area='SUPPLY')
        # E o vizinho de fora não entra.
        Lancamento.objects.create(categoria=self.despesa, valor='99.00',
                                  data=date(2027, 1, 1), area='SUPPLY')
        self.assertEqual(self._linha(situacao_dos_tetos(date(2026, 9, 1)), 'SUPPLY')['gasto'],
                         Decimal('20.00'))

    def test_numero_fixo_de_consultas(self):
        TetoArea.objects.create(area='SUPPLY', valor='100.00')
        TetoArea.objects.create(area='RECREACAO', valor='100.00')
        self._gasto('SUPPLY', '30.00')
        self._gasto('VIOLETA', '30.00')
        with self.assertNumQueries(2):
            situacao_dos_tetos(self.referencia)


class TetoAreaModelTest(TestCase):
    def test_uma_area_nao_pode_ter_dois_tetos(self):
        """O teto perpetua até alguém alterar. Dois na mesma área deixariam
        ninguém sabendo qual vale."""
        from django.db import IntegrityError
        TetoArea.objects.create(area='SUPPLY', valor='10.00')
        with self.assertRaises(IntegrityError):
            TetoArea.objects.create(area='SUPPLY', valor='20.00')


class GastoPorAreaTest(TestCase):
    def setUp(self):
        self.despesa = Categoria.objects.create(nome='Materiais', tipo='DESPESA')
        self.receita = Categoria.objects.create(nome='Doação', tipo='RECEITA')
        for area, valor in (('SUPPLY', '300.00'), ('RECREACAO', '100.00'), ('SUPPLY', '100.00')):
            Lancamento.objects.create(
                categoria=self.despesa, valor=valor, data=date(2026, 8, 10), area=area
            )
        Lancamento.objects.create(
            categoria=self.receita, valor='9000.00', data=date(2026, 8, 10), area='SUPPLY'
        )

    def test_agrupa_e_ordena_do_maior_para_o_menor(self):
        linhas, total = gasto_por_area(date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(total, Decimal('500.00'))
        self.assertEqual([linha['area'] for linha in linhas], ['SUPPLY', 'RECREACAO'])
        self.assertEqual(linhas[0]['valor'], Decimal('400.00'))
        self.assertEqual(linhas[0]['lancamentos'], 2)
        self.assertEqual(linhas[0]['percentual'], Decimal('80.0'))
        self.assertEqual(linhas[0]['nome'], 'Supply')

    def test_gasto_sem_area_recebe_rotulo_honesto(self):
        Lancamento.objects.create(
            categoria=self.despesa, valor='700.00', data=date(2026, 8, 11), area=''
        )
        linhas, _ = gasto_por_area(date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(linhas[0]['nome'], SEM_AREA)

    def test_periodo_sem_gasto_devolve_vazio(self):
        linhas, total = gasto_por_area(date(2020, 1, 1), date(2020, 12, 31))
        self.assertEqual(linhas, [])
        self.assertEqual(total, Decimal('0'))


class SemestreEscolhidoTest(TestCase):
    """Link torto no grupo do WhatsApp não pode virar erro 500 na tela que
    todos os voluntários abrem."""

    def test_vazio_cai_no_semestre_atual(self):
        self.assertEqual(_semestre_escolhido(''), timezone.localdate())

    def test_semestre_valido_e_respeitado(self):
        self.assertEqual(_semestre_escolhido('2026-1'), date(2026, 1, 1))
        self.assertEqual(_semestre_escolhido('2026-2'), date(2026, 7, 1))

    def test_numero_invalido_cai_no_padrao(self):
        for bruto in ('2026-3', '2026-0', '2026-13'):
            with self.subTest(bruto=bruto):
                self.assertEqual(_semestre_escolhido(bruto), timezone.localdate())

    def test_texto_qualquer_cai_no_padrao(self):
        for bruto in ('semestre passado', '2026', 'abc-1', '99999-1'):
            with self.subTest(bruto=bruto):
                self.assertEqual(_semestre_escolhido(bruto), timezone.localdate())

    def test_limites_do_semestre(self):
        from adm.servicos import limites_do_semestre
        self.assertEqual(limites_do_semestre(date(2026, 3, 9)),
                         (date(2026, 1, 1), date(2026, 6, 30)))
        self.assertEqual(limites_do_semestre(date(2026, 7, 1)),
                         (date(2026, 7, 1), date(2026, 12, 31)))


class AcessoDasTelasNovasTest(TestCase):
    """A tela de tetos é a única do Financeiro aberta a qualquer voluntário: o
    pedido é que cada um veja a situação do teto da sua área sem depender do ADM.
    Conta e recarga continuam fechadas."""

    def setUp(self):
        self.fabrica = RequestFactory()
        self.comum = User.objects.create_user(
            username='vol_comum', password='pw', area='RECREACAO'
        )
        self.financeiro = User.objects.create_user(
            username='vol_fin', password='pw', area='ADM/FIN'
        )

    def _gate_liberou(self, view, url, usuario):
        """True se a view deixou passar.

        RequestFactory porque o test Client quebra ao copiar o contexto do
        template neste ambiente. O template é entrega de outro agente, então
        TemplateDoesNotExist conta como liberado: o que se prova é a permissão.
        """
        requisicao = self.fabrica.get(url)
        requisicao.user = usuario
        try:
            view(requisicao)
        except PermissionDenied:
            return False
        except TemplateDoesNotExist:
            return True
        return True

    def test_voluntario_comum_ve_tetos(self):
        self.assertTrue(self._gate_liberou(view_tetos, '/adm/tetos/', self.comum))

    def test_voluntario_comum_nao_ve_contas(self):
        self.assertFalse(self._gate_liberou(view_contas, '/adm/contas/', self.comum))

    def test_voluntario_comum_nao_ve_recargas(self):
        self.assertFalse(self._gate_liberou(view_recargas, '/adm/contas/recargas/', self.comum))

    def test_financeiro_ve_contas(self):
        self.assertTrue(self._gate_liberou(view_contas, '/adm/contas/', self.financeiro))

    def test_contas_responde_403_pela_url(self):
        cliente = Client()
        cliente.force_login(self.comum)
        self.assertEqual(cliente.get('/adm/contas/').status_code, 403)

    def test_tetos_sem_login_redireciona(self):
        self.assertEqual(Client().get('/adm/tetos/').status_code, 302)

    def test_rotas_registradas(self):
        self.assertEqual(reverse('adm:contas'), '/adm/contas/')
        self.assertEqual(reverse('adm:conta_criar'), '/adm/contas/nova/')
        self.assertEqual(reverse('adm:conta_editar', args=[7]), '/adm/contas/7/editar/')
        self.assertEqual(reverse('adm:recargas'), '/adm/contas/recargas/')
        self.assertEqual(reverse('adm:recarga_criar'), '/adm/contas/recargas/nova/')
        self.assertEqual(reverse('adm:recarga_editar', args=[7]), '/adm/contas/recargas/7/editar/')
        self.assertEqual(reverse('adm:tetos'), '/adm/tetos/')
        self.assertEqual(reverse('adm:teto_criar'), '/adm/tetos/novo/')
        self.assertEqual(reverse('adm:teto_editar', args=[7]), '/adm/tetos/7/editar/')
        self.assertEqual(reverse('adm:reembolsos'), '/adm/reembolsos/')
        self.assertEqual(reverse('adm:reembolso_pagar', args=[7]), '/adm/reembolsos/7/pagar/')


class TetosContextoTest(TestCase):
    """O voluntário precisa achar a linha da própria área sem procurar."""

    def setUp(self):
        self.fabrica = RequestFactory()
        despesa = Categoria.objects.create(nome='Materiais', tipo='DESPESA')
        self.referencia = timezone.localdate()
        TetoArea.objects.create(area='RECREACAO', valor='200.00')
        Lancamento.objects.create(
            categoria=despesa, valor='50.00', data=self.referencia, area='RECREACAO'
        )

    def _contexto(self, usuario):
        requisicao = self.fabrica.get('/adm/tetos/')
        requisicao.user = usuario
        with patch('adm.views.render') as render_falso:
            view_tetos(requisicao)
        return render_falso.call_args[0][2]

    def test_minha_linha_e_a_da_area_do_usuario(self):
        usuario = User.objects.create_user(username='rec_teto', password='pw', area='RECREACAO')
        contexto = self._contexto(usuario)
        self.assertEqual(contexto['minha_linha']['area'], 'RECREACAO')
        self.assertEqual(contexto['minha_linha']['gasto'], Decimal('50.00'))
        self.assertFalse(contexto['pode_editar'])

    def test_area_sem_teto_nem_gasto_nao_tem_linha(self):
        usuario = User.objects.create_user(username='mkt_teto', password='pw', area='MARKETING')
        self.assertIsNone(self._contexto(usuario)['minha_linha'])

    def test_financeiro_pode_editar(self):
        usuario = User.objects.create_user(username='fin_teto', password='pw', area='ADM/FIN')
        self.assertTrue(self._contexto(usuario)['pode_editar'])


# ─── Reembolso pago ───

# Upload real de comprovante: sem isto os arquivos de teste caem no media/ do
# projeto e ficam lá para sempre.
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ReembolsoPagoTest(TestCase):
    def setUp(self):
        self.fabrica = RequestFactory()
        self.cliente = Client()
        self.adm = User.objects.create_user(
            username='fin_pag', password='pw', area='ADM/FIN', email='fin@pcf.org'
        )
        self.solicitante = User.objects.create_user(
            username='vol_pag', password='pw', area='RECREACAO', email='vol@pcf.org'
        )
        self.categoria = Categoria.objects.create(nome='Materiais', tipo='DESPESA')
        self.conta = Conta.objects.create(nome='BB', tipo='BANCO')
        self.evento = Evento.objects.create(nome='PC Feijuca', data=date(2026, 8, 15))
        self.pedido = PedidoReembolso.objects.create(
            solicitante=self.solicitante, valor='120.00', descricao='Tinta e pincel',
            data_gasto=date(2026, 8, 2), categoria=self.categoria,
            comprovante='reembolsos/nota.jpg', status='APROVADO',
        )
        # Lançamento nasce na aprovação; o pagamento apenas o completa.
        sincronizar_lancamento_do_reembolso(self.pedido, self.adm)
        self.pedido.save()
        self.cliente.force_login(self.adm)
        self.url = reverse('adm:reembolso_pagar', args=[self.pedido.pk])

    def _comprovante(self):
        return SimpleUploadedFile('pix.png', b'conteudo-falso', content_type='image/png')

    def _dados(self, **extra):
        dados = {
            'conta_pagamento': self.conta.pk,
            'pago_em': '2026-08-20',
            'area': 'RECREACAO',
            'evento': self.evento.pk,
            'comprovante_pagamento': self._comprovante(),
        }
        dados.update(extra)
        return dados

    def test_form_exige_comprovante_e_conta(self):
        form = PagamentoReembolsoForm(
            data={'pago_em': '2026-08-20', 'area': 'RECREACAO'}, instance=self.pedido
        )
        self.assertFalse(form.is_valid())
        self.assertIn('conta_pagamento', form.errors)
        self.assertIn('comprovante_pagamento', form.errors)

    def test_post_sem_comprovante_nao_paga(self):
        requisicao = self.fabrica.post(self.url, {'conta_pagamento': self.conta.pk})
        requisicao.user = self.adm
        try:
            reembolso_pagar(requisicao, pk=self.pedido.pk)
        except TemplateDoesNotExist:
            pass  # o template é de outro agente; o que importa é não ter pago
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'APROVADO')
        self.assertIsNone(self.pedido.pago_em)

    def test_pagamento_grava_quem_quando_e_conta(self):
        resposta = self.cliente.post(self.url, self._dados())
        self.assertEqual(resposta.status_code, 302)

        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'PAGO')
        self.assertEqual(self.pedido.pago_por, self.adm)
        self.assertEqual(self.pedido.pago_em, date(2026, 8, 20))
        self.assertEqual(self.pedido.conta_pagamento, self.conta)
        self.assertTrue(self.pedido.comprovante_pagamento)

    def test_comprovante_do_gasto_nao_e_sobrescrito_pelo_do_pagamento(self):
        self.cliente.post(self.url, self._dados())
        self.pedido.refresh_from_db()
        # São provas de lados diferentes: reaproveitar um campo apagaria uma.
        self.assertEqual(self.pedido.comprovante.name, 'reembolsos/nota.jpg')
        self.assertIn('reembolsos_pagos/', self.pedido.comprovante_pagamento.name)

    def test_pagamento_manda_email_ao_solicitante(self):
        mail.outbox = []
        self.cliente.post(self.url, self._dados())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['vol@pcf.org'])
        self.assertIn('120.00', mail.outbox[0].body)
        self.assertIn('BB', mail.outbox[0].body)

    def test_falha_de_email_nao_desfaz_o_pagamento(self):
        """O dinheiro saiu de verdade: SMTP fora do ar não pode desfazer isso."""
        with patch('adm.views.send_mail', side_effect=Exception('smtp fora do ar')):
            resposta = self.cliente.post(self.url, self._dados())
        self.assertEqual(resposta.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'PAGO')
        self.assertEqual(self.pedido.pago_por, self.adm)

    def test_solicitante_sem_email_nao_derruba_pagamento(self):
        self.solicitante.email = ''
        self.solicitante.save()
        mail.outbox = []
        self.cliente.post(self.url, self._dados())
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'PAGO')
        self.assertEqual(len(mail.outbox), 0)

    def test_lancamento_leva_area_evento_e_conta(self):
        self.cliente.post(self.url, self._dados())
        self.pedido.refresh_from_db()
        lancamento = self.pedido.lancamento
        # Sem os três o gasto não conta no teto da área nem no evento.
        self.assertEqual(lancamento.area, 'RECREACAO')
        self.assertEqual(lancamento.evento, self.evento)
        self.assertEqual(lancamento.conta, self.conta)
        self.assertEqual(lancamento.origem, 'REEMBOLSO')
        self.assertEqual(lancamento.tipo, 'DESPESA')

    def test_gasto_do_reembolso_entra_no_teto_da_area(self):
        self.cliente.post(self.url, self._dados())
        self.pedido.refresh_from_db()
        TetoArea.objects.create(area='RECREACAO', valor='200.00')

        referencia = self.pedido.lancamento.data
        linha = next(l for l in situacao_dos_tetos(referencia) if l['area'] == 'RECREACAO')
        self.assertEqual(linha['gasto'], Decimal('120.00'))
        self.assertEqual(linha['disponivel'], Decimal('80.00'))

    def test_pagamento_nao_duplica_lancamento(self):
        antes = Lancamento.objects.count()
        self.cliente.post(self.url, self._dados())
        self.assertEqual(Lancamento.objects.count(), antes)

    def test_pedido_pendente_nao_pode_ser_pago(self):
        pendente = PedidoReembolso.objects.create(
            solicitante=self.solicitante, valor='10.00', descricao='x',
            data_gasto=date(2026, 8, 2), categoria=self.categoria,
            comprovante='reembolsos/x.jpg', status='PENDENTE',
        )
        resposta = self.cliente.post(
            reverse('adm:reembolso_pagar', args=[pendente.pk]), self._dados()
        )
        self.assertEqual(resposta.status_code, 302)
        pendente.refresh_from_db()
        self.assertEqual(pendente.status, 'PENDENTE')

    def test_pagar_duas_vezes_e_recusado(self):
        self.cliente.post(self.url, self._dados())
        antes = Lancamento.objects.count()
        resposta = self.cliente.post(self.url, self._dados())
        self.assertEqual(resposta.status_code, 302)
        # Pagar de novo geraria despesa em dobro.
        self.assertEqual(Lancamento.objects.count(), antes)

    def test_voluntario_comum_nao_paga_reembolso(self):
        cliente = Client()
        cliente.force_login(User.objects.create_user(
            username='rec_pag', password='pw', area='RECREACAO'
        ))
        self.assertEqual(cliente.post(self.url, self._dados()).status_code, 403)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.status, 'APROVADO')


class DoacaoLevaContaTest(TestCase):
    """A doação precisa dizer qual banco recebeu, senão o saldo da conta ignora
    o dinheiro que entrou."""

    def test_contribuicao_copia_conta_para_o_lancamento(self):
        from parceiros.models import Contribuicao, Parceiro

        conta = Conta.objects.create(nome='Caju', tipo='CARTAO', controla_saldo=True)
        parceiro = Parceiro.objects.create(nome='Padaria do Zé')
        contribuicao = Contribuicao.objects.create(
            parceiro=parceiro, competencia=date(2026, 8, 1), valor='250.00',
            data_recebimento=date(2026, 8, 5), conta=conta,
        )
        contribuicao.refresh_from_db()
        self.assertEqual(contribuicao.lancamento.conta, conta)
        self.assertEqual(contribuicao.lancamento.tipo, 'RECEITA')


class SupplyEntraNoFinanceiroTest(TestCase):
    """O pedido do Supply é a maior fonte de gasto do projeto. Três defeitos
    aqui deixavam dinheiro invisível — todos travados abaixo."""

    def setUp(self):
        from supply.models import Item
        self.item = Item.objects.create(nome='Papel A4', unidade='UN')
        self.pedinte = User.objects.create_user(
            username='pede', password='x', area='SUPPLY')

    def _pedido(self, **campos):
        from supply.models import Pedido
        campos.setdefault('nome', 'Papel A4')
        campos.setdefault('quantidade', Decimal('10'))
        campos.setdefault('valor', Decimal('5.00'))
        campos.setdefault('area', 'SUPPLY')
        return Pedido.objects.create(item=self.item, requisitado_por=self.pedinte, **campos)

    def test_entra_mesmo_sem_a_categoria_existir(self):
        """Antes o sinal desistia em silêncio: o pedido era salvo, o dinheiro
        saía e nada aparecia no Financeiro — sem erro para ninguém notar."""
        Categoria.objects.filter(nome='Materiais Supply').delete()

        pedido = self._pedido()

        lancamento = Lancamento.objects.filter(pedido=pedido).first()
        self.assertIsNotNone(lancamento, 'gasto do Supply não pode sumir por falta de categoria')
        self.assertEqual(lancamento.origem, 'SUPPLY')
        self.assertEqual(lancamento.tipo, 'DESPESA')

    def test_lanca_o_valor_TOTAL_e_nao_o_unitario(self):
        """`valor` é o unitário. Lançar ele em vez de `valor_total` fazia um
        pedido de 10 unidades a R$ 5 entrar como R$ 5 — dez vezes menos."""
        pedido = self._pedido(quantidade=Decimal('10'), valor=Decimal('5.00'))

        lancamento = Lancamento.objects.get(pedido=pedido)
        self.assertEqual(lancamento.valor, Decimal('50.00'))
        self.assertEqual(lancamento.valor, pedido.valor_total)

    def test_leva_a_area_do_pedido(self):
        """Sem a área, o gasto do Supply não contava no teto do Supply."""
        pedido = self._pedido(area='RECREACAO')
        self.assertEqual(Lancamento.objects.get(pedido=pedido).area, 'RECREACAO')

    def test_pedido_sem_area_nao_inventa_uma(self):
        pedido = self._pedido(area=None)
        self.assertEqual(Lancamento.objects.get(pedido=pedido).area, '')

    def test_editar_o_pedido_corrige_o_lancamento(self):
        pedido = self._pedido(quantidade=Decimal('10'))
        pedido.quantidade = Decimal('20')
        pedido.area = 'AZUL'
        pedido.save()

        lancamento = Lancamento.objects.get(pedido=pedido)
        self.assertEqual(lancamento.valor, Decimal('100.00'))
        self.assertEqual(lancamento.area, 'AZUL')

    def test_tirar_o_valor_remove_o_lancamento(self):
        pedido = self._pedido()
        pedido.valor = None
        pedido.save()
        self.assertFalse(Lancamento.objects.filter(pedido=pedido).exists())

    def test_gasto_do_supply_conta_no_teto_da_area(self):
        """O encontro das duas pontas: pedido do Supply vira gasto no teto."""
        from adm.models import TetoArea
        TetoArea.objects.create(area='SUPPLY', valor='500.00')
        pedido = self._pedido(quantidade=Decimal('10'), valor=Decimal('5.00'),
                              sabado=None)
        Lancamento.objects.filter(pedido=pedido).update(data=timezone.localdate())

        linha = next(l for l in situacao_dos_tetos(timezone.localdate())
                     if l['area'] == 'SUPPLY')

        self.assertEqual(linha['gasto'], Decimal('50.00'))
        self.assertEqual(linha['disponivel'], Decimal('450.00'))

    def test_categoria_desativada_nao_esconde_o_gasto(self):
        """Alguém desativar a categoria pela tela não pode fazer o gasto
        desaparecer do Financeiro."""
        Categoria.objects.update_or_create(
            nome='Materiais Supply', defaults={'tipo': 'RECEITA', 'ativo': False})

        pedido = self._pedido()

        lancamento = Lancamento.objects.get(pedido=pedido)
        self.assertEqual(lancamento.tipo, 'DESPESA')
        self.assertTrue(lancamento.categoria.ativo)


class CompletarLancamentoAutomaticoTest(TestCase):
    """Lançamento automático não se edita — mas alguém precisa poder dizer de
    qual cartão saiu o dinheiro, senão o gasto do Supply fica para sempre sem
    banco e o pedido do ADM ("toda entrada e saída com o banco") não fecha."""

    def setUp(self):
        self.financeiro = User.objects.create_user(
            username='fin', password='x', area='ADM/FIN')
        self.comum = User.objects.create_user(
            username='zeca', password='x', area='RECREACAO')
        self.conta = Conta.objects.create(nome='Caju 09', tipo='CARTAO', controla_saldo=True)
        categoria = Categoria.objects.create(nome='Materiais', tipo='DESPESA')
        self.automatico = Lancamento.objects.create(
            categoria=categoria, valor=Decimal('40.00'),
            data=timezone.localdate(), origem='SUPPLY')
        self.manual = Lancamento.objects.create(
            categoria=categoria, valor=Decimal('10.00'),
            data=timezone.localdate(), origem='MANUAL')
        self.cliente = Client()

    def _url(self, lancamento):
        return reverse('adm:completar_lancamento', args=[lancamento.pk])

    def test_financeiro_define_conta_e_area(self):
        self.cliente.force_login(self.financeiro)
        resposta = self.cliente.post(self._url(self.automatico),
                                     {'conta': self.conta.pk, 'area': 'SUPPLY'})

        self.assertEqual(resposta.status_code, 302)
        self.automatico.refresh_from_db()
        self.assertEqual(self.automatico.conta, self.conta)
        self.assertEqual(self.automatico.area, 'SUPPLY')

    def test_nao_mexe_em_valor_data_nem_categoria(self):
        """O POST pode mandar qualquer coisa; o form só aceita conta e área."""
        self.cliente.force_login(self.financeiro)
        self.cliente.post(self._url(self.automatico), {
            'conta': self.conta.pk, 'area': 'SUPPLY',
            'valor': '99999.00', 'data': '2000-01-01',
        })
        self.automatico.refresh_from_db()
        self.assertEqual(self.automatico.valor, Decimal('40.00'))
        self.assertEqual(self.automatico.data, timezone.localdate())

    def test_conta_definida_entra_no_saldo_do_cartao(self):
        """O encontro das pontas: definir a conta faz o gasto descontar o saldo."""
        self.cliente.force_login(self.financeiro)
        self.cliente.post(self._url(self.automatico),
                          {'conta': self.conta.pk, 'area': 'SUPPLY'})
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.total_gasto, Decimal('40.00'))

    def test_lancamento_manual_e_mandado_para_a_edicao_normal(self):
        self.cliente.force_login(self.financeiro)
        resposta = self.cliente.post(self._url(self.manual), {'conta': self.conta.pk})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(str(self.manual.pk), resposta.url)

    def test_voluntario_comum_nao_entra(self):
        self.cliente.force_login(self.comum)
        with self.assertRaises(PermissionDenied):
            requisicao = RequestFactory().get(self._url(self.automatico))
            requisicao.user = self.comum
            completar_lancamento(requisicao, pk=self.automatico.pk)
