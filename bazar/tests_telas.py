"""Testes das telas do Bazar.

RequestFactory, sem `self.client`: o test client do Django copia o contexto do
template e essa cópia quebra no Python 3.14 (Django 4.2 suporta até 3.12).
Chamando a view direto, os templates DE VERDADE são renderizados — que é
justamente o que precisa ser conferido numa tela que vai rodar com fila na
frente.
"""
import json
from datetime import date

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from atendido.models import Atendido
from voluntario.models import Voluntario

from . import views
from .models import Bazar, Categoria, Retirada


class BaseTela(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.bazar = Bazar.objects.create(
            nome="Bazar 2026", cota_inicial=5, etapa=Bazar.Etapa.PRIMEIRA)
        self.camiseta = Categoria.objects.create(
            bazar=self.bazar, nome="Camiseta", pontos=1, estoque_inicial=100)
        self.calcado = Categoria.objects.create(
            bazar=self.bazar, nome="Calçado", pontos=3, estoque_inicial=4)

        self.voluntario = Voluntario.objects.create_user(
            username="maria", password="senha-de-teste-123", area="VIOLETA")
        self.coordenacao = Voluntario.objects.create_user(
            username="lia", password="senha-de-teste-123", area="EVENTOS")

        self.joao = Atendido.objects.create(
            nome="João Pedro Silva", sala="VIOLETA",
            data_nascimento=date(2015, 3, 10))

    def pedido(self, caminho, usuario, metodo="get", dados=None):
        request = getattr(self.factory, metodo)(caminho, dados or {})
        request.user = usuario
        request.session = {}
        request._messages = FallbackStorage(request)
        return request


class AtendimentoTest(BaseTela):

    def test_qualquer_voluntario_logado_atende(self):
        """Quem está escalado no dia é voluntário comum, não a coordenação."""
        resposta = views.atendimento(self.pedido("/bazar/", self.voluntario))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Camiseta", resposta.content.decode())

    def test_sem_bazar_aberto_a_tela_explica(self):
        self.bazar.etapa = Bazar.Etapa.NAO_COMECOU
        self.bazar.save()
        html = views.atendimento(
            self.pedido("/bazar/", self.voluntario)).content.decode()

        self.assertIn("Nenhum Bazar aberto", html)
        self.assertNotIn("Finalizar retirada", html)

    def test_os_botoes_mostram_o_valor_em_pontos(self):
        """O voluntário não pode precisar decorar a tabela de preços."""
        html = views.atendimento(
            self.pedido("/bazar/", self.voluntario)).content.decode()
        self.assertIn("3 pontos", html)


class BuscaTest(BaseTela):

    def buscar(self, termo):
        resposta = views.buscar_atendido(
            self.pedido(f"/bazar/buscar/?q={termo}", self.voluntario))
        return json.loads(resposta.content)

    def test_acha_por_parte_do_nome(self):
        self.assertEqual(
            self.buscar("pedro")["resultados"][0]["nome"], "João Pedro Silva")

    def test_uma_letra_nao_busca(self):
        """Uma letra devolveria o projeto inteiro e não ajudaria ninguém."""
        self.assertEqual(self.buscar("j")["resultados"], [])

    def test_atendido_inativo_nao_aparece(self):
        self.joao.ativo = False
        self.joao.save()
        self.assertEqual(self.buscar("pedro")["resultados"], [])

    def test_a_sala_vem_junto_para_confirmar_a_pessoa(self):
        """Nome repetido acontece; a salinha é o desempate na hora."""
        self.assertEqual(self.buscar("pedro")["resultados"][0]["sala"], "Violeta")


class SituacaoTest(BaseTela):

    def situacao(self, atendido=None):
        alvo = atendido or self.joao
        resposta = views.situacao(
            self.pedido(f"/bazar/situacao/{alvo.pk}/", self.voluntario), alvo.pk)
        return json.loads(resposta.content)

    def test_traz_saldo_e_cota(self):
        dados = self.situacao()
        self.assertEqual(dados["saldo"], 5)
        self.assertEqual(dados["cota"], 5)
        self.assertFalse(dados["ja_retirou"])

    def test_traz_a_numeracao_da_ficha(self):
        self.joao.numeracao_camisa = "10"
        self.joao.save()
        self.assertEqual(self.situacao()["numeracoes"]["camisa"], "10")

    def test_na_segunda_etapa_o_saldo_vem_nulo(self):
        self.bazar.etapa = Bazar.Etapa.SEGUNDA
        self.bazar.save()
        dados = self.situacao()
        self.assertIsNone(dados["saldo"])
        self.assertFalse(dados["desconta_pontos"])


class FinalizarTest(BaseTela):

    def finalizar(self, dados, usuario=None):
        resposta = views.finalizar(
            self.pedido("/bazar/finalizar/", usuario or self.voluntario,
                        metodo="post", dados=dados))
        return resposta.status_code, json.loads(resposta.content)

    def test_registra_e_devolve_o_resumo(self):
        codigo, corpo = self.finalizar({
            "atendido": self.joao.pk,
            f"qtd_{self.camiseta.pk}": 2,
        })
        self.assertEqual(codigo, 200)
        self.assertEqual(corpo["total"], 2)
        self.assertEqual(corpo["pecas"], 2)
        self.assertTrue(Retirada.objects.filter(atendido=self.joao).exists())

    def test_pontos_insuficientes_devolve_409_com_o_motivo(self):
        """409 e não 400: a requisição está certa, a regra do Bazar é que barrou."""
        codigo, corpo = self.finalizar({
            "atendido": self.joao.pk,
            f"qtd_{self.calcado.pk}": 2,       # 6 > 5
        })
        self.assertEqual(codigo, 409)
        self.assertIn("Pontos insuficientes", corpo["erro"])
        self.assertFalse(Retirada.objects.exists())

    def test_segunda_passagem_e_recusada(self):
        self.finalizar({"atendido": self.joao.pk, f"qtd_{self.camiseta.pk}": 1})
        codigo, corpo = self.finalizar(
            {"atendido": self.joao.pk, f"qtd_{self.camiseta.pk}": 1})

        self.assertEqual(codigo, 409)
        self.assertIn("já finalizou", corpo["erro"])

    def test_registra_quem_conferiu_e_quem_levou(self):
        self.finalizar({
            "atendido": self.joao.pk,
            f"qtd_{self.camiseta.pk}": 1,
            "retirado_por": Retirada.RetiradoPor.PAI_MAE,
            "retirado_por_nome": "Ana",
            "sala_do_bazar": "Sala 2",
        })
        retirada = Retirada.objects.get()
        self.assertEqual(retirada.conferido_por, self.voluntario)
        self.assertEqual(retirada.retirado_por_nome, "Ana")
        self.assertEqual(retirada.sala_do_bazar, "Sala 2")

    def test_estoque_estourado_registra_e_avisa(self):
        """Avisa, não bloqueia: a peça já está na mão do voluntário."""
        self.calcado.estoque_inicial = 1
        self.calcado.save()
        codigo, corpo = self.finalizar({
            "atendido": self.joao.pk,
            f"qtd_{self.camiseta.pk}": 2,
            f"qtd_{self.calcado.pk}": 1,
        })
        self.assertEqual(codigo, 200)
        self.assertEqual(corpo["alertas"], [])   # 1 de 1 ainda cabe

        maria = Atendido.objects.create(
            nome="Maria", sala="AZUL", data_nascimento=date(2016, 1, 1))
        codigo2, corpo2 = self.finalizar({
            "atendido": maria.pk, f"qtd_{self.calcado.pk}": 1})

        self.assertEqual(codigo2, 200)           # entregou assim mesmo
        self.assertTrue(corpo2["alertas"])


class CoordenacaoTest(BaseTela):

    def test_voluntario_comum_nao_abre_o_painel(self):
        with self.assertRaises(PermissionDenied):
            views.painel(self.pedido("/bazar/painel/", self.voluntario))

    def test_eventos_e_triade_abrem(self):
        resposta = views.painel(self.pedido("/bazar/painel/", self.coordenacao))
        self.assertEqual(resposta.status_code, 200)

    def test_a_chave_da_etapa_e_manual(self):
        views.mudar_etapa(
            self.pedido(f"/bazar/{self.bazar.pk}/etapa/", self.coordenacao,
                        metodo="post", dados={"etapa": Bazar.Etapa.SEGUNDA}),
            self.bazar.pk)

        self.bazar.refresh_from_db()
        self.assertEqual(self.bazar.etapa, Bazar.Etapa.SEGUNDA)

    def test_nao_deixa_abrir_um_segundo_bazar(self):
        outro = Bazar.objects.create(
            nome="Outro", etapa=Bazar.Etapa.NAO_COMECOU)
        views.mudar_etapa(
            self.pedido(f"/bazar/{outro.pk}/etapa/", self.coordenacao,
                        metodo="post", dados={"etapa": Bazar.Etapa.PRIMEIRA}),
            outro.pk)

        outro.refresh_from_db()
        self.assertEqual(outro.etapa, Bazar.Etapa.NAO_COMECOU)

    def test_o_painel_mostra_os_numeros_do_dia(self):
        views.finalizar(self.pedido(
            "/bazar/finalizar/", self.voluntario, metodo="post",
            dados={"atendido": self.joao.pk, f"qtd_{self.camiseta.pk}": 2}))

        html = views.painel(
            self.pedido("/bazar/painel/", self.coordenacao)).content.decode()
        self.assertIn("João Pedro Silva", html)
        self.assertIn("peças distribuídas", html)


class RelatorioTest(BaseTela):

    def test_csv_tem_uma_linha_por_peca(self):
        """Uma linha por peça deixa a planilha somar por categoria, salinha ou
        etapa sem ninguém desmontar nada."""
        views.finalizar(self.pedido(
            "/bazar/finalizar/", self.voluntario, metodo="post",
            dados={"atendido": self.joao.pk,
                   f"qtd_{self.camiseta.pk}": 2,
                   f"qtd_{self.calcado.pk}": 1}))

        resposta = views.relatorio(
            self.pedido(f"/bazar/{self.bazar.pk}/relatorio/", self.coordenacao),
            self.bazar.pk)
        texto = resposta.content.decode("utf-8")

        self.assertIn("text/csv", resposta["Content-Type"])
        linhas = [l for l in texto.splitlines() if l.strip()]
        self.assertEqual(len(linhas), 3)           # cabeçalho + duas categorias
        self.assertIn("João Pedro Silva", texto)
        self.assertIn("Violeta", texto)

    def test_o_csv_abre_certo_no_excel(self):
        """Sem o BOM, o Excel mostra "João" como "JoÃ£o"."""
        views.finalizar(self.pedido(
            "/bazar/finalizar/", self.voluntario, metodo="post",
            dados={"atendido": self.joao.pk, f"qtd_{self.camiseta.pk}": 1}))

        resposta = views.relatorio(
            self.pedido(f"/bazar/{self.bazar.pk}/relatorio/", self.coordenacao),
            self.bazar.pk)
        self.assertTrue(resposta.content.decode("utf-8").startswith("﻿"))

    def test_voluntario_comum_nao_baixa_o_relatorio(self):
        with self.assertRaises(PermissionDenied):
            views.relatorio(
                self.pedido(f"/bazar/{self.bazar.pk}/relatorio/", self.voluntario),
                self.bazar.pk)
