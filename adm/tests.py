from django.test import TestCase, RequestFactory, Client
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from django.template import TemplateDoesNotExist
from django.urls import reverse
from unittest.mock import MagicMock, patch
from datetime import date
from decimal import Decimal
from adm.models import Categoria, Lancamento
from adm.servicos import SEM_CATEGORIA, _linha_despesa, despesas_por_categoria
from adm.views import (
    AdmAcessoMixin, AdmEscritaMixin, _periodo_prestacao_contas, onde_investimos,
)
from forms_pcf.models import ReceptorNotificacaoReembolso, PedidoReembolso

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
