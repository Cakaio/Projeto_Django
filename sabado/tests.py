"""Testes do resumo de disponibilidade do sábado.

O que está sob teste é uma pergunta de gestão: QUEM AINDA NÃO RESPONDEU. Errar
essa conta tem custo real — a liderança cobra gente errada, ou deixa de cobrar
quem falta.

Observação sobre RequestFactory: a view é chamada direto, sem `self.client`. O
test client do Django copia o contexto do template ao renderizar, e essa cópia
quebra no Python 3.14 — o Django 4.2 só suporta até o 3.12. É falha do
ambiente, não do app.
"""
import datetime
from unittest import mock

from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from sabado import views
from sabado.models import DisponibilidadeVoluntario, Sabado
from voluntario.models import Voluntario


def criar_voluntario(username, area='RECREACAO', **extras):
    return Voluntario.objects.create_user(
        username=username, password='senha-de-teste',
        first_name=username.capitalize(), area=area, **extras)


def contexto_de(usuario, sabado=None):
    """Roda a view e devolve o contexto que ela montou.

    `render()` devolve um HttpResponse, que não carrega o contexto; e o test
    client, que carregaria, quebra ao renderizar neste ambiente. Interceptar o
    `render` é o caminho que exercita a view inteira sem tocar no código de
    produção só para poder testá-lo.
    """
    requisicao = RequestFactory().get(
        reverse('sabado:resumo_sabado'),
        {'sabado': sabado.pk} if sabado else {})
    requisicao.user = usuario

    capturado = {}

    def render_falso(pedido, template, contexto=None, *args, **kwargs):
        capturado.update(contexto or {})
        return HttpResponse('ok')

    with mock.patch('sabado.views.render', side_effect=render_falso):
        views.resumo_sabado(requisicao)
    return capturado


class VoluntariosAtivosTests(TestCase):
    """A regra de 'quem está no projeto hoje' mora num lugar só."""

    def test_ativos_exclui_desligado_e_login_desativado(self):
        criar_voluntario('ativo')
        criar_voluntario('saiu', data_saida=datetime.date(2026, 1, 10))
        criar_voluntario('bloqueado', is_active=False)

        ativos = list(Voluntario.objects.ativos())

        self.assertEqual([v.username for v in ativos], ['ativo'])

    def test_manager_continua_criando_usuario(self):
        """O manager customizado herda de UserManager: trocá-lo por um genérico
        quebraria `create_user` e o `createsuperuser`."""
        usuario = Voluntario.objects.create_user(
            username='novo', password='x', area='SUPPLY')
        self.assertTrue(usuario.check_password('x'))


class QuemNaoRespondeuTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sabado = Sabado.objects.create(
            data=datetime.date(2026, 9, 12), tema='Pertencimento', descricao='—')

        cls.vai = criar_voluntario('ana', area='AZUL')
        cls.nao_vai = criar_voluntario('bruno', area='AZUL')
        cls.calado = criar_voluntario('carla', area='VERDE')
        cls.calado2 = criar_voluntario('davi', area='AZUL')
        # Estes dois não podem aparecer em lugar nenhum da conta.
        cls.desligado = criar_voluntario('elena', data_saida=datetime.date(2026, 2, 1))
        cls.bloqueado = criar_voluntario('felipe', is_active=False)

        cls.triade = criar_voluntario('gestora', area='TRIADE')

        DisponibilidadeVoluntario.objects.create(
            sabado=cls.sabado, voluntario=cls.vai, vai_ao_projeto=True)
        DisponibilidadeVoluntario.objects.create(
            sabado=cls.sabado, voluntario=cls.nao_vai, vai_ao_projeto=False)

    def contexto(self, usuario=None):
        return contexto_de(usuario or self.triade, self.sabado)

    def test_quem_disse_que_nao_vai_sai_da_fila_de_cobranca(self):
        """Responder 'não vou' É responder. O erro clássico é continuar
        cobrando quem já se posicionou."""
        contexto = self.contexto()
        pendentes = {v.username for g in contexto['nao_responderam_por_area']
                     for v in g['voluntarios']}
        self.assertNotIn('bruno', pendentes)
        self.assertEqual(contexto['total_nao_vao'], 1)

    def test_desligado_e_bloqueado_nunca_entram_na_conta(self):
        contexto = self.contexto()
        pendentes = {v.username for g in contexto['nao_responderam_por_area']
                     for v in g['voluntarios']}
        self.assertNotIn('elena', pendentes)
        self.assertNotIn('felipe', pendentes)
        # Ana, Bruno, Carla, Davi e a gestora — os 5 ativos.
        self.assertEqual(contexto['total_ativos'], 5)

    def test_lista_so_quem_falta_mesmo(self):
        contexto = self.contexto()
        pendentes = {v.username for g in contexto['nao_responderam_por_area']
                     for v in g['voluntarios']}
        self.assertEqual(pendentes, {'carla', 'davi', 'gestora'})
        self.assertEqual(contexto['total_nao_responderam'], 3)

    def test_agrupa_por_area(self):
        """Cada líder cobra a própria equipe, em vez de uma lista única."""
        contexto = self.contexto()
        por_area = {g['nome']: {v.username for v in g['voluntarios']}
                    for g in contexto['nao_responderam_por_area']}
        self.assertEqual(por_area['Azul'], {'davi'})
        self.assertEqual(por_area['Verde'], {'carla'})
        # Área sem ninguém pendente não vira um bloco vazio na tela.
        self.assertNotIn('Marketing', por_area)

    def test_percentual_bate_com_a_lista(self):
        contexto = self.contexto()
        self.assertEqual(contexto['total_responderam'], 2)      # ana e bruno
        self.assertEqual(contexto['percentual_resposta'], 40)   # 2 de 5

    def test_percentual_nao_divide_por_zero(self):
        Voluntario.objects.update(data_saida=datetime.date(2026, 1, 1))
        anonimo = criar_voluntario('zeca', area='AZUL')
        contexto = contexto_de(anonimo, self.sabado)
        self.assertIsInstance(contexto['percentual_resposta'], int)


class QuemNaoVaiEhRestritoTests(TestCase):
    """'Não vou' costuma ter motivo pessoal atrás. O número serve para
    planejar o sábado; os nomes, não."""

    @classmethod
    def setUpTestData(cls):
        cls.sabado = Sabado.objects.create(
            data=datetime.date(2026, 9, 19), tema='T', descricao='—')
        cls.faltante = criar_voluntario('ana', area='AZUL')
        DisponibilidadeVoluntario.objects.create(
            sabado=cls.sabado, voluntario=cls.faltante, vai_ao_projeto=False)

    def test_triade_e_gestao_de_talentos_veem_os_nomes(self):
        for area in ('TRIADE', 'GESTAO_DE_TALENTOS'):
            with self.subTest(area=area):
                usuario = criar_voluntario(f'chefe_{area.lower()}', area=area)
                contexto = contexto_de(usuario, self.sabado)
                self.assertTrue(contexto['pode_ver_quem_nao_vai'])
                self.assertEqual([v.username for v in contexto['voluntarios_nao_vao']],
                                 ['ana'])

    def test_outra_area_ve_so_o_numero(self):
        usuario = criar_voluntario('zeca', area='RECREACAO')
        contexto = contexto_de(usuario, self.sabado)
        self.assertFalse(contexto['pode_ver_quem_nao_vai'])
        self.assertEqual(contexto['voluntarios_nao_vao'], [])
        self.assertEqual(contexto['total_nao_vao'], 1)   # o número continua


class ResumoExigeLoginTests(TestCase):
    """A tela mostra nome de voluntário e painel de saúde: não pode ficar
    aberta. Faltava o decorator — todas as outras views do app já o tinham."""

    def test_anonimo_e_mandado_para_o_login(self):
        resposta = self.client.get(reverse('sabado:resumo_sabado'))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn('/login', resposta.url)


class LembreteTests(TestCase):

    def test_nao_cobra_quem_saiu_do_projeto(self):
        """O lembrete ia para todo mundo já cadastrado, então ex-voluntário
        continuava recebendo cobrança de uma enquete que não é mais dele."""
        from django.core import mail
        from django.core.management import call_command
        from io import StringIO

        # A enquete fecha 3 dias antes; o lembrete sai 1 dia antes disso.
        sabado = Sabado.objects.create(
            data=datetime.datetime.now().date() + datetime.timedelta(days=4),
            tema='T', descricao='—')
        criar_voluntario('ativo', email='ativo@pcf.org')
        criar_voluntario('saiu', email='saiu@pcf.org',
                         data_saida=datetime.date(2026, 1, 1))
        criar_voluntario('bloqueado', email='bloqueado@pcf.org', is_active=False)

        call_command('lembrete_disponibilidade', stdout=StringIO())

        destinatarios = {e for msg in mail.outbox for e in msg.recipients()}
        self.assertEqual(destinatarios, {'ativo@pcf.org'})
        self.assertTrue(sabado.enquete_aberta)
