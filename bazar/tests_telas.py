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

        # "Nenhum Bazar aberto" parecia defeito para quem abriu a tela. Agora
        # diz o que falta e a quem pedir.
        self.assertIn("ainda não abriu", html)
        self.assertNotIn("data-conferir", html)

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
        self.assertIn("já foi registrada", corpo["erro"])

    def test_registra_quem_conferiu_e_quem_levou(self):
        """A sala virou lista: a tela manda o id, não o texto digitado."""
        from .models import SalaDoBazar
        sala = SalaDoBazar.objects.create(bazar=self.bazar, nome="Sala 2")
        self.finalizar({
            "atendido": self.joao.pk,
            f"qtd_{self.camiseta.pk}": 1,
            "retirado_por": Retirada.RetiradoPor.PAI_MAE,
            "retirado_por_nome": "Ana",
            "sala": sala.pk,
        })
        retirada = Retirada.objects.get()
        self.assertEqual(retirada.conferido_por, self.voluntario)
        self.assertEqual(retirada.retirado_por_nome, "Ana")
        self.assertEqual(retirada.sala, sala)

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


class BuscaComIdadeTest(BaseTela):
    """Duas "Maria Eduarda" do Amarelo são hoje duas linhas idênticas na lista,
    e a retirada vai para a criança errada — erro que a trava da etapa depois
    torna caro de desfazer, porque a criança certa passa a ser barrada.
    """

    def test_busca_devolve_idade_e_numeracoes(self):
        self.joao.numeracao_camisa = "10"
        self.joao.numeracao_calca = "8"
        self.joao.save()

        resposta = views.buscar_atendido(
            self.pedido("/bazar/buscar/?q=Jo", self.voluntario))
        linha = json.loads(resposta.content)["resultados"][0]

        self.assertEqual(linha["nome"], "João Pedro Silva")
        self.assertIn("idade", linha)
        self.assertEqual(linha["numeracoes"]["camisa"], "10")
        self.assertEqual(linha["numeracoes"]["calca"], "8")

    def test_ficha_sem_nascimento_nao_derruba_a_busca(self):
        """`data_nascimento` é NOT NULL hoje, mas a busca não pode depender
        disso: o dia em que o campo virar opcional, a fila não pode parar."""
        class FichaSemData:
            data_nascimento = None

        self.assertIsNone(views.idade_de(FichaSemData()))

    def test_idade_conta_o_aniversario_que_ainda_nao_chegou(self):
        from datetime import timedelta
        from django.utils import timezone as tz

        class Ficha:
            pass

        hoje = tz.localdate()
        amanha = hoje + timedelta(days=1)
        ficha = Ficha()
        ficha.data_nascimento = date(hoje.year - 10, amanha.month, amanha.day)
        # Faz 10 amanhã, então hoje tem 9.
        self.assertEqual(views.idade_de(ficha), 9)


class ColisaoEntreDuasSalasTest(BaseTela):
    """Duas salas conferindo a mesma criança ao mesmo tempo.

    A checagem acontece antes da gravação, então a corrida existe. Hoje o
    IntegrityError da constraint sobe cru e vira 500 no celular do voluntário,
    com a sacola já na mão.
    """

    def test_colisao_responde_409_e_nao_estoura(self):
        from .regras import finalizar_retirada
        finalizar_retirada(bazar=self.bazar, atendido=self.joao,
                           pedido={self.camiseta.pk: 1},
                           conferido_por=self.coordenacao)

        resposta = views.finalizar(self.pedido(
            "/bazar/finalizar/", self.voluntario, metodo="post",
            dados={"atendido": self.joao.pk, f"qtd_{self.camiseta.pk}": 1}))

        self.assertEqual(resposta.status_code, 409)
        self.assertIn("erro", json.loads(resposta.content))

    def test_o_recado_diz_quando_e_quem_registrou(self):
        from .regras import finalizar_retirada
        finalizar_retirada(bazar=self.bazar, atendido=self.joao,
                           pedido={self.camiseta.pk: 1},
                           conferido_por=self.coordenacao)

        resposta = views.finalizar(self.pedido(
            "/bazar/finalizar/", self.voluntario, metodo="post",
            dados={"atendido": self.joao.pk, f"qtd_{self.camiseta.pk}": 1}))

        recado = json.loads(resposta.content)["erro"]
        self.assertIn("João Pedro Silva", recado)
        self.assertIn("lia", recado)
        self.assertIn("Nada foi gravado duas vezes", recado)


class FinalizarComOsCamposNovosTest(BaseTela):
    def test_visitante_pela_tela(self):
        resposta = views.finalizar(self.pedido(
            "/bazar/finalizar/", self.voluntario, metodo="post",
            dados={"visitante_nome": "Irmão do João",
                   "visitante_motivo": "veio com a mãe",
                   f"qtd_{self.camiseta.pk}": 2}))

        self.assertEqual(resposta.status_code, 200)
        retirada = Retirada.objects.get()
        self.assertIsNone(retirada.atendido)
        self.assertEqual(retirada.visitante_nome, "Irmão do João")

    def test_veio_e_nao_levou_nada_pela_tela(self):
        resposta = views.finalizar(self.pedido(
            "/bazar/finalizar/", self.voluntario, metodo="post",
            dados={"atendido": self.joao.pk, "sem_retirada": "1"}))

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(Retirada.objects.get().sem_retirada)

    def test_a_sala_escolhida_e_gravada(self):
        from .models import SalaDoBazar
        sala = SalaDoBazar.objects.create(bazar=self.bazar, nome="Sala 2")
        views.finalizar(self.pedido(
            "/bazar/finalizar/", self.voluntario, metodo="post",
            dados={"atendido": self.joao.pk, f"qtd_{self.camiseta.pk}": 1,
                   "sala": sala.pk}))
        self.assertEqual(Retirada.objects.get().sala, sala)

    def test_reenvio_com_o_mesmo_token_nao_duplica(self):
        dados = {"atendido": self.joao.pk, f"qtd_{self.camiseta.pk}": 1,
                 "token": "abc-123"}
        views.finalizar(self.pedido("/bazar/finalizar/", self.voluntario,
                                    metodo="post", dados=dados))
        resposta = views.finalizar(self.pedido("/bazar/finalizar/", self.voluntario,
                                               metodo="post", dados=dados))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Retirada.objects.count(), 1)


class CancelarPelaTelaTest(BaseTela):
    def _gravar(self):
        from .regras import finalizar_retirada
        retirada, _, _ = finalizar_retirada(
            bazar=self.bazar, atendido=self.joao,
            pedido={self.camiseta.pk: 1}, conferido_por=self.voluntario)
        return retirada

    def test_quem_conferiu_cancela_e_a_trava_reabre(self):
        from .regras import ja_retirou_nesta_etapa
        retirada = self._gravar()

        resposta = views.cancelar(
            self.pedido("/bazar/cancelar/", self.voluntario, metodo="post",
                        dados={"motivo": "marquei errado"}),
            pk=retirada.pk)

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(ja_retirou_nesta_etapa(self.bazar, self.joao))

    def test_cancelar_sem_motivo_responde_409(self):
        retirada = self._gravar()
        resposta = views.cancelar(
            self.pedido("/bazar/cancelar/", self.voluntario, metodo="post",
                        dados={"motivo": ""}),
            pk=retirada.pk)
        self.assertEqual(resposta.status_code, 409)

    def test_get_nao_cancela(self):
        """Cancelar muda estado: não pode acontecer por alguém abrir uma URL."""
        from django.http import HttpResponseNotAllowed
        retirada = self._gravar()
        resposta = views.cancelar(
            self.pedido("/bazar/cancelar/", self.voluntario), pk=retirada.pk)
        self.assertIsInstance(resposta, HttpResponseNotAllowed)


class TelaDoCaixaTest(BaseTela):
    """A tela renderizada de verdade.

    Cada teste aqui trava um defeito que estava na tela antiga e que foi o
    motivo do redesenho — não são preferências de layout.
    """

    def _html(self, usuario=None):
        return views.atendimento(
            self.pedido("/bazar/", usuario or self.voluntario)).content.decode()

    def test_diz_o_que_fazer_antes_de_escolher_alguem(self):
        """A tela abria com um campo de busca solto e nada mais: quem nunca viu
        não tem como saber que o primeiro passo é digitar o nome."""
        self.assertIn("PASSO 1", self._html().upper())

    def test_o_menos_e_botao_proprio_e_nao_span_dentro_do_botao(self):
        """O `−` era um <span> de 32px DENTRO do <button> que soma: errar o
        alvo não era neutro, adicionava peça. E <span> não é focável, então
        dava para somar pelo teclado e não dava para tirar."""
        html = self._html()
        self.assertNotIn('<span class="bz-menos"', html)
        self.assertIn('data-menos', html)
        # O menos é um botão de verdade.
        trecho = html[html.index('data-menos') - 200:html.index('data-menos')]
        self.assertIn('<button', trecho)

    def test_nenhum_campo_de_digitacao_abaixo_de_16px(self):
        """Abaixo de 16px o iOS dá zoom sozinho ao focar e desalinha a tela no
        meio do atendimento. Vale para CAMPO, não para texto: legenda de
        estoque a 0.7rem está certa e não pode ser arrastada junto."""
        import re
        html = self._html()
        bloco = html[html.index("<style>"):html.index("</style>")]

        for seletor, corpo in re.findall(r'([^{}]+)\{([^{}]*)\}', bloco):
            if not re.search(r'\b(input|select|textarea)\b', seletor):
                continue
            for tamanho in re.findall(r'font-size:\s*([\d.]+)rem', corpo):
                with self.subTest(seletor=seletor.strip()):
                    self.assertGreaterEqual(
                        float(tamanho) * 16, 15.99,
                        f"{seletor.strip()} tem font-size {tamanho}rem — "
                        "abaixo de 16px o iOS dá zoom ao focar")

    def test_o_rodape_fixo_traz_saldo_sacola_e_o_botao(self):
        """O saldo morava num cartão no topo, que sai da tela exatamente
        enquanto se marca peça."""
        html = self._html()
        self.assertIn("data-saldo-numero", html)
        self.assertIn("data-total", html)
        self.assertIn("data-conferir", html)

    def test_o_rodape_respeita_a_barra_do_iphone(self):
        """sticky/fixed bottom:0 se ancora no viewport de layout do iOS: sem
        safe-area o botão fica atrás da barra de gestos."""
        html = self._html()
        self.assertIn("safe-area-inset-bottom", html)

    def test_o_botao_verde_confere_antes_de_gravar(self):
        """Um toque acidental no botão que ocupa a largura inteira gravava e
        travava a criança naquela etapa."""
        html = self._html()
        self.assertIn("data-folha", html)
        self.assertIn("data-confirmar", html)

    def test_oferece_o_caminho_de_quem_nao_esta_cadastrado(self):
        self.assertIn("data-visitante", self._html())

    def test_oferece_veio_e_nao_levou_nada(self):
        self.assertIn("data-sem-retirada", self._html())

    def test_lista_as_salas_do_bazar(self):
        from .models import SalaDoBazar
        SalaDoBazar.objects.create(bazar=self.bazar, nome="Sala 1", ordem=1)
        self.assertIn("Sala 1", self._html())

    def test_diz_a_cota_da_etapa_por_extenso(self):
        """O primeiro número grande da tela é "5 pontos": ou a tela explica, ou
        o voluntário chuta."""
        self.assertIn("5", self._html())

    def test_sem_bazar_aberto_a_tela_explica_em_vez_de_parecer_erro(self):
        self.bazar.etapa = Bazar.Etapa.NAO_COMECOU
        self.bazar.save()
        html = self._html()
        self.assertIn("coordena", html.lower())

    def test_o_js_carrega_com_carimbo_de_versao(self):
        """Sem o `?v=`, publicar uma correção não entrega nada a quem já abriu
        o site — o endereço não muda e o navegador serve o arquivo velho."""
        self.assertIn("bazar-atendimento.js?v=", self._html())


class SituacaoCompletaTest(BaseTela):
    """O que a tela precisa saber sobre a criança, de uma vez só."""

    def _situacao(self):
        resposta = views.situacao(
            self.pedido(f"/bazar/situacao/{self.joao.pk}/", self.voluntario),
            pk=self.joao.pk)
        return json.loads(resposta.content)

    def test_devolve_a_idade(self):
        self.assertIsNotNone(self._situacao()["idade"])

    def test_quem_ja_passou_recebe_a_frase_inteira(self):
        """"Já passou" sem hora nem sala não diz a quem perguntar — e é isso
        que o voluntário precisa saber, com a roupa na mão."""
        from .models import SalaDoBazar
        from .regras import finalizar_retirada
        sala = SalaDoBazar.objects.create(bazar=self.bazar, nome="Sala 2")
        finalizar_retirada(bazar=self.bazar, atendido=self.joao,
                           pedido={self.camiseta.pk: 1},
                           conferido_por=self.coordenacao, sala=sala)

        dados = self._situacao()

        self.assertTrue(dados["ja_retirou"])
        self.assertIn("Sala 2", dados["recado_ja_retirou"])
        self.assertIn("lia", dados["recado_ja_retirou"])

    def test_quem_nao_passou_nao_recebe_frase(self):
        self.assertEqual(self._situacao()["recado_ja_retirou"], "")


class VisitanteNoPainelEnoRelatorioTest(BaseTela):
    """`atendido` passou a aceitar nulo. Todo lugar que lia `atendido.nome`
    direto precisa saber disso — no CSV isso estoura de verdade."""

    def setUp(self):
        super().setUp()
        from .regras import finalizar_retirada
        finalizar_retirada(
            bazar=self.bazar, atendido=None, pedido={self.camiseta.pk: 1},
            conferido_por=self.voluntario, visitante_nome="Irmão do João",
            visitante_motivo="veio com a mãe")

    def test_o_painel_mostra_o_nome_do_visitante(self):
        html = views.painel(
            self.pedido("/bazar/painel/", self.coordenacao)).content.decode()
        self.assertIn("Irmão do João", html)

    def test_o_relatorio_csv_nao_estoura_com_visitante(self):
        resposta = views.relatorio(
            self.pedido(f"/bazar/{self.bazar.pk}/relatorio/", self.coordenacao),
            pk=self.bazar.pk)
        corpo = resposta.content.decode("utf-8")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Irmão do João", corpo)


class PainelUsaODesignDoProjetoTest(BaseTela):
    """O painel reinventava borda, raio e sombra próprios — é parte do "não
    parece do mesmo sistema"."""

    def _html(self):
        return views.painel(
            self.pedido("/bazar/painel/", self.coordenacao)).content.decode()

    def test_usa_as_classes_do_projeto(self):
        html = self._html()
        for classe in ("pcf-page-head", "pcf-kpi", "pcf-table"):
            with self.subTest(classe=classe):
                self.assertIn(classe, html)

    def test_o_kit_de_papel_e_alcancavel(self):
        """O plano B não vale nada se ninguém achar onde imprimir."""
        self.assertIn(f"/bazar/{self.bazar.pk}/kit/", self._html())


class KitAlcancavelDoCaixaTest(BaseTela):
    def test_a_tela_de_atendimento_leva_ao_kit_de_papel(self):
        """Quem está no caixa é que precisa imprimir — e o painel é da
        coordenação, que ele não abre."""
        html = views.atendimento(
            self.pedido("/bazar/", self.voluntario)).content.decode()
        self.assertIn(f"/bazar/{self.bazar.pk}/kit/", html)
