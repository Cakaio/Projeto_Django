"""Cadastrar caixa sem passar pelo admin, e a busca dizendo a verdade.

QUEM COORDENA O BAZAR NAO NECESSARIAMENTE ENTRA NO ADMIN: `pode_coordenar` e
superusuario OU area TRIADE/EVENTOS, e o admin do Django exige `is_staff`, que
e outra flag. O painel mandava a coordenacao para "Configurar" e metade dela
batia numa tela de login — por isso nenhuma caixa estava cadastrada no dia.
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from atendido.models import Atendido
from bazar.models import Bazar, Categoria, Retirada, SalaDoBazar

Voluntario = get_user_model()


class CadastroDeCaixasTests(TestCase):

    def setUp(self):
        self.coord = Voluntario.objects.create_user(
            username='eventos', password='x', area='EVENTOS')
        self.bazar = Bazar.objects.create(
            nome='Edicao', data=timezone.localdate(),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=20, criado_por=self.coord)
        self.client.force_login(self.coord)
        self.url = f'/bazar/{self.bazar.pk}/caixas/'

    def test_coordenacao_cria_caixa_sem_ser_staff(self):
        self.assertFalse(self.coord.is_staff)   # o ponto do teste

        self.client.post(self.url, {'acao': 'criar', 'nome': 'Mesa da entrada'})

        self.assertTrue(self.bazar.salas.filter(nome='Mesa da entrada').exists())

    def test_nome_repetido_e_recusado_com_motivo(self):
        """Duas "Mesa 1" na mesma edicao deixariam o relatorio sem como dizer
        de qual saiu a peca."""
        SalaDoBazar.objects.create(bazar=self.bazar, nome='Mesa 1', ordem=1)

        self.client.post(self.url, {'acao': 'criar', 'nome': 'Mesa 1'})

        self.assertEqual(self.bazar.salas.filter(nome='Mesa 1').count(), 1)

    def test_nome_vazio_nao_cria(self):
        self.client.post(self.url, {'acao': 'criar', 'nome': '   '})
        self.assertEqual(self.bazar.salas.count(), 0)

    def test_renomear(self):
        caixa = SalaDoBazar.objects.create(bazar=self.bazar, nome='Mesa 1', ordem=1)

        self.client.post(self.url, {'acao': 'renomear', 'caixa': caixa.pk,
                                    'nome': 'Recepção'})

        caixa.refresh_from_db()
        self.assertEqual(caixa.nome, 'Recepção')

    def test_desativar_tira_da_tela_sem_apagar(self):
        caixa = SalaDoBazar.objects.create(bazar=self.bazar, nome='Mesa 1', ordem=1)

        self.client.post(self.url, {'acao': 'alternar', 'caixa': caixa.pk})

        caixa.refresh_from_db()
        self.assertFalse(caixa.ativo)
        self.assertTrue(SalaDoBazar.objects.filter(pk=caixa.pk).exists())

    def test_caixa_sem_uso_pode_ser_excluida(self):
        caixa = SalaDoBazar.objects.create(bazar=self.bazar, nome='Mesa 1', ordem=1)

        self.client.post(self.url, {'acao': 'excluir', 'caixa': caixa.pk})

        self.assertFalse(SalaDoBazar.objects.filter(pk=caixa.pk).exists())

    def test_caixa_ja_usada_nao_e_apagada(self):
        """`Retirada.sala` e PROTECT: apagar apagaria a origem no relatorio.
        A recusa precisa ser recusa, com motivo e saida — nao um 500."""
        caixa = SalaDoBazar.objects.create(bazar=self.bazar, nome='Mesa 1', ordem=1)
        crianca = Atendido.objects.create(
            nome='Maria', data_nascimento=datetime.date(2015, 1, 1),
            sala='AMARELO', ativo=True)
        Retirada.objects.create(bazar=self.bazar, atendido=crianca, sala=caixa,
                                etapa=Retirada.Etapa.PRIMEIRA,
                                conferido_por=self.coord,
                                finalizada_em=timezone.now())

        resposta = self.client.post(self.url, {'acao': 'excluir',
                                               'caixa': caixa.pk})

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(SalaDoBazar.objects.filter(pk=caixa.pk).exists())

    def test_quem_nao_coordena_nao_mexe(self):
        outro = Voluntario.objects.create_user(
            username='amarelo', password='x', area='AMARELO')
        self.client.force_login(outro)

        self.client.post(self.url, {'acao': 'criar', 'nome': 'Invasora'})

        self.assertFalse(self.bazar.salas.filter(nome='Invasora').exists())

    def test_get_nao_mexe(self):
        """Cadastrar muda estado: nao pode acontecer por abrir uma URL."""
        resposta = self.client.get(self.url)
        self.assertIn(resposta.status_code, (403, 405))


class BuscaDizAVerdadeTests(TestCase):
    """A tela acusava a crianca de nao existir quando o problema era outro."""

    def setUp(self):
        self.pessoa = Voluntario.objects.create_user(
            username='caixa1', password='x', area='EVENTOS')
        self.bazar = Bazar.objects.create(
            nome='Edicao', data=timezone.localdate(),
            etapa=Bazar.Etapa.PRIMEIRA, cota_inicial=20, criado_por=self.pessoa)
        self.client.force_login(self.pessoa)

    def test_atendido_inativo_vira_AVISO_e_nao_silencio(self):
        Atendido.objects.create(nome='Joana Inativa', sala='AZUL', ativo=False,
                                data_nascimento=datetime.date(2014, 1, 1))

        dados = self.client.get('/bazar/buscar/', {'q': 'joana'}).json()

        self.assertEqual(dados['resultados'], [])
        self.assertIn('INATIVO', dados['aviso'])
        self.assertIn('Joana Inativa', dados['aviso'])

    def test_nome_que_nao_existe_nao_inventa_aviso(self):
        dados = self.client.get('/bazar/buscar/', {'q': 'zzzz'}).json()

        self.assertEqual(dados['resultados'], [])
        self.assertNotIn('aviso', dados)
