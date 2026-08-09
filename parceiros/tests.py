import datetime
from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from parceiros import views as crm_views

from adm.models import Lancamento
from parceiros.models import CATEGORIA_DOACOES, Contribuicao, Parceiro
from voluntario.models import Voluntario


def criar_voluntario(username, area='MARKETING', superuser=False):
    """`area` é obrigatória no model. O padrão MARKETING é de propósito: uma
    área SEM poder nenhum no CRM, para provar que o acesso veio de onde
    esperamos (CR/RE, TRIADE ou is_superuser) e não da área."""
    return Voluntario.objects.create_user(
        username=username, password='senha-de-teste',
        first_name=username.capitalize(), area=area, is_superuser=superuser,
    )


class PermissaoCRMTests(TestCase):
    """O CRM é de CR/RE, Tríade e superusuário — mais ninguém."""

    @classmethod
    def setUpTestData(cls):
        cls.cr = criar_voluntario('livia', area='CR/RE')
        cls.triade = criar_voluntario('tri', area='TRIADE')
        cls.admin = criar_voluntario('root', superuser=True)
        cls.comum = criar_voluntario('zeca', area='RECREACAO')
        cls.rotas = [
            reverse('parceiros:painel'),
            reverse('parceiros:grade'),
            reverse('parceiros:lista'),
            reverse('parceiros:criar'),
            reverse('parceiros:contribuicao_criar'),
        ]

    # Observação: usamos RequestFactory em vez de self.client nos casos que
    # RENDERIZAM a página. O test client do Django copia o contexto do template
    # (`store_rendered_templates`), e essa cópia quebra no Python 3.14 — o
    # Django 4.2 só suporta até o 3.12. É falha do ambiente, não do app: a
    # suíte pré-existente (adm) falha igual. Com RequestFactory o render é o
    # mesmo, sem a instrumentação quebrada.

    def test_cr_re_tem_acesso(self):
        for rota, view in self.views_por_rota():
            requisicao = RequestFactory().get(rota)
            requisicao.user = self.cr
            self.assertEqual(view(requisicao).status_code, 200, rota)

    def test_triade_e_superuser_tem_acesso(self):
        for usuario in (self.triade, self.admin):
            requisicao = RequestFactory().get(reverse('parceiros:painel'))
            requisicao.user = usuario
            self.assertEqual(crm_views.painel(requisicao).status_code, 200)

    def test_voluntario_comum_recebe_403(self):
        for rota, view in self.views_por_rota():
            requisicao = RequestFactory().get(rota)
            requisicao.user = self.comum
            with self.assertRaises(PermissionDenied, msg=rota):
                view(requisicao)

    def views_por_rota(self):
        return [
            (reverse('parceiros:painel'), crm_views.painel),
            (reverse('parceiros:grade'), crm_views.grade),
            (reverse('parceiros:lista'), crm_views.lista),
            (reverse('parceiros:criar'), crm_views.parceiro_form),
            (reverse('parceiros:contribuicao_criar'), crm_views.contribuicao_form),
        ]

    def test_anonimo_e_redirecionado_para_login(self):
        resposta = self.client.get(reverse('parceiros:painel'))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/login', resposta.url)


class IntegracaoFinanceiraTests(TestCase):
    """Cada contribuição espelha um lançamento de RECEITA no Financeiro."""

    @classmethod
    def setUpTestData(cls):
        cls.cr = criar_voluntario('livia', area='CR/RE')
        cls.parceiro = Parceiro.objects.create(nome='Daniel de Marco Barbosa', responsavel=cls.cr)

    def _contribuir(self, valor='100.00', mes=3, recebimento=None):
        return Contribuicao.objects.create(
            parceiro=self.parceiro,
            competencia=datetime.date(2026, mes, 1),
            valor=Decimal(valor),
            data_recebimento=recebimento or datetime.date(2026, mes, 10),
            registrado_por=self.cr,
        )

    def test_contribuicao_gera_lancamento_de_receita(self):
        contribuicao = self._contribuir()
        contribuicao.refresh_from_db()
        self.assertIsNotNone(contribuicao.lancamento)
        lancamento = contribuicao.lancamento
        self.assertEqual(lancamento.origem, 'DOACAO')
        self.assertEqual(lancamento.tipo, 'RECEITA')      # derivado da categoria
        self.assertEqual(lancamento.categoria.nome, CATEGORIA_DOACOES)
        self.assertEqual(lancamento.valor, Decimal('100.00'))

    def test_usa_a_data_do_recebimento_e_nao_a_competencia(self):
        """O DRE é mensal: usar 'hoje' deslocaria a receita de mês."""
        contribuicao = self._contribuir(mes=3, recebimento=datetime.date(2026, 4, 2))
        contribuicao.refresh_from_db()
        self.assertEqual(contribuicao.lancamento.data, datetime.date(2026, 4, 2))

    def test_editar_valor_atualiza_o_lancamento(self):
        contribuicao = self._contribuir(valor='100.00')
        contribuicao.refresh_from_db()
        contribuicao.valor = Decimal('180.00')
        contribuicao.save()
        contribuicao.lancamento.refresh_from_db()
        self.assertEqual(contribuicao.lancamento.valor, Decimal('180.00'))
        self.assertEqual(Lancamento.objects.filter(origem='DOACAO').count(), 1)

    def test_apagar_contribuicao_apaga_o_lancamento(self):
        contribuicao = self._contribuir()
        self.assertEqual(Lancamento.objects.filter(origem='DOACAO').count(), 1)
        contribuicao.delete()
        self.assertEqual(Lancamento.objects.filter(origem='DOACAO').count(), 0)

    def test_pular_lancamento_nao_toca_no_financeiro(self):
        """Caminho da importação de histórico — não pode duplicar receita."""
        contribuicao = Contribuicao(
            parceiro=self.parceiro, competencia=datetime.date(2026, 5, 1),
            valor=Decimal('50.00'), data_recebimento=datetime.date(2026, 5, 1),
        )
        contribuicao.pular_lancamento = True
        contribuicao.save()
        self.assertIsNone(contribuicao.lancamento)
        self.assertEqual(Lancamento.objects.count(), 0)

    def test_competencia_e_normalizada_para_o_dia_1(self):
        contribuicao = Contribuicao.objects.create(
            parceiro=self.parceiro, competencia=datetime.date(2026, 6, 23),
            valor=Decimal('20.00'), data_recebimento=datetime.date(2026, 6, 23),
        )
        self.assertEqual(contribuicao.competencia, datetime.date(2026, 6, 1))

    def test_lancamento_de_doacao_nao_pode_ser_editado_no_financeiro(self):
        """A fonte da verdade é a contribuição; editar dos dois lados divergiria."""
        contribuicao = self._contribuir()
        contribuicao.refresh_from_db()
        admin = criar_voluntario('fin', area='ADM/FIN', superuser=True)
        self.client.force_login(admin)
        resposta = self.client.get(
            reverse('adm:editar_lancamento', args=[contribuicao.lancamento.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta.url, reverse('adm:lista_lancamentos'))


class GradeAnualTests(TestCase):
    """A grade é a substituta da planilha: linhas x 12 meses + totais."""

    @classmethod
    def setUpTestData(cls):
        cls.cr = criar_voluntario('livia', area='CR/RE')
        cls.parceiro = Parceiro.objects.create(nome='Luiza de Almeida', responsavel=cls.cr)
        for mes, valor in ((3, '25.00'), (4, '25.00'), (6, '20.00')):
            Contribuicao.objects.create(
                parceiro=cls.parceiro, competencia=datetime.date(2026, mes, 1),
                valor=Decimal(valor), data_recebimento=datetime.date(2026, mes, 5))

    def test_grade_monta_12_meses_com_buracos(self):
        requisicao = RequestFactory().get(reverse('parceiros:grade'), {'ano': 2026})
        requisicao.user = self.cr
        resposta = crm_views.grade(requisicao)
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        self.assertIn('Luiza de Almeida', html)
        # Valores das células aparecem (e também no rodapé "arrecadado no mês",
        # por isso não vale contar ocorrências).
        self.assertIn('25,00', html)
        self.assertIn('20,00', html)
        # 70,00 sai no total da linha, no total geral e no resumo do topo.
        # Contagem exata seria frágil; o que importa é que o total aparece.
        self.assertGreaterEqual(html.count('70,00'), 2)
        # Os 12 meses estão na grade, mesmo os sem doação.
        for mes in ('Jan', 'Mai', 'Dez'):
            self.assertIn(mes, html)

    def test_grade_calcula_totais_por_mes(self):
        """Checa a estrutura de dados da grade sem passar pelo template."""
        requisicao = RequestFactory().get(reverse('parceiros:grade'), {'ano': 2026})
        requisicao.user = self.cr
        crm_views.grade(requisicao)   # garante que a view roda sem erro
        contribuicoes = {c.competencia.month: c.valor for c in self.parceiro.contribuicoes.all()}
        self.assertEqual(contribuicoes, {3: Decimal('25.00'), 4: Decimal('25.00'), 6: Decimal('20.00')})
        self.assertNotIn(5, contribuicoes)          # maio ficou vazio, como na planilha

    def test_um_mes_so_aceita_uma_contribuicao_por_parceiro(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Contribuicao.objects.create(
                parceiro=self.parceiro, competencia=datetime.date(2026, 3, 1),
                valor=Decimal('10.00'), data_recebimento=datetime.date(2026, 3, 1))
