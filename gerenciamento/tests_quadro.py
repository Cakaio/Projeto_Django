"""Testes do filtro e do resumo do quadro de pautas.

As views são chamadas direto pelo RequestFactory, sem `self.client`: o test
client copia o contexto do template e essa cópia quebra no Python 3.14 (o
Django 4.2 só suporta até o 3.12). É falha do ambiente, não do app — e chamando
a view direto os templates DE VERDADE são exercitados, que é justamente o que
estes testes precisam conferir.
"""
from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from voluntario.models import Grupo, Voluntario

from .models import CienciaPauta, Pauta
from .views import DIAS_DE_CONCLUIDAS_NO_QUADRO, pautas as view_quadro


class BaseQuadro(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.grupo = Grupo.objects.create(
            nome="Lideranças", regras=[{"areas": [], "cargos": ["LIDER"]}])
        self.outro_grupo = Grupo.objects.create(
            nome="Conselho", regras=[{"areas": [], "cargos": ["LIDER"]}])

        self.lider = Voluntario.objects.create_user(
            username="lider", password="senha-de-teste-123",
            area="VIOLETA", cargo="LIDER", first_name="Lia", last_name="Dias")
        self.colega = Voluntario.objects.create_user(
            username="colega", password="senha-de-teste-123",
            area="SUPPLY", first_name="Caio", last_name="Nunes")

    def pauta(self, titulo="Pauta", **extras):
        dados = {
            "titulo": titulo,
            "descricao": "Descrição da pauta.",
            "criado_por": self.colega,
            "emitido_por_area": self.colega.area,
            "prazo_ddl": timezone.now() + timedelta(days=3),
            "grupo": self.grupo,
        }
        dados.update(extras)
        return Pauta.objects.create(**dados)

    def abrir(self, consulta=""):
        pedido = self.factory.get("/gerenciamento/" + consulta)
        pedido.user = self.lider
        resposta = view_quadro(pedido)
        return resposta.content.decode()


class ResumoTest(BaseQuadro):
    """Os quatro números que respondem "o que preciso olhar?"."""

    def test_conta_o_total_do_quadro(self):
        for i in range(3):
            self.pauta(f"Pauta {i}")
        self.assertIn("<strong>3</strong> no quadro", self.abrir())

    def test_conta_as_que_esperam_minha_ciencia(self):
        vista = self.pauta("Já vi")
        CienciaPauta.objects.create(pauta=vista, voluntario=self.lider)
        self.pauta("Não vi ainda")

        self.assertIn("<strong>1</strong> esperando sua ciência", self.abrir())

    def test_concluida_nao_entra_na_conta_de_ciencia_pendente(self):
        """Cobrar ciência de assunto encerrado é ruído."""
        self.pauta("Encerrada", status=Pauta.Status.CONCLUIDA)
        self.assertIn("<strong>0</strong> esperando sua ciência", self.abrir())

    def test_conta_as_atrasadas(self):
        self.pauta("No prazo")
        self.pauta("Estourou", prazo_ddl=timezone.now() - timedelta(days=2))

        self.assertIn("<strong>1</strong> atrasada", self.abrir())

    def test_concluida_nunca_conta_como_atrasada(self):
        self.pauta("Entregue tarde, mas entregue",
                   prazo_ddl=timezone.now() - timedelta(days=2),
                   status=Pauta.Status.CONCLUIDA)
        self.assertIn("<strong>0</strong> atrasada", self.abrir())

    def test_conta_as_minhas(self):
        minha = self.pauta("Sou responsável")
        minha.responsaveis.add(self.lider)
        self.pauta("De outra pessoa")

        self.assertIn("<strong>1</strong> sob sua responsabilidade", self.abrir())

    def test_atalho_sem_nada_para_mostrar_vem_desligado(self):
        """Botão que não filtraria nada não deve convidar ao clique."""
        self.pauta("Só uma")   # sem responsável: "minhas" fica em zero
        self.assertTrue(self._atalho_desabilitado("minhas", self.abrir()))

    def test_atalho_com_resultado_fica_clicavel(self):
        minha = self.pauta("Sou responsável")
        minha.responsaveis.add(self.lider)
        self.assertFalse(self._atalho_desabilitado("minhas", self.abrir()))

    def _atalho_desabilitado(self, atalho, html):
        """Procura `disabled` dentro da tag do atalho, sem depender do formato.

        Afirmar a string exata amarraria o teste à ordem e à quebra de linha
        dos atributos no template — detalhe de formatação, não de comportamento.
        """
        marca = f'data-quick="{atalho}"'
        inicio = html.find(marca)
        self.assertNotEqual(inicio, -1, f'atalho "{atalho}" não está na página')
        abertura = html.rfind("<button", 0, inicio)
        fim = html.find(">", inicio)
        return "disabled" in html[abertura:fim]


class ConcluidasAntigasTest(BaseQuadro):
    """A coluna Concluída não pode virar arquivo morto.

    Cada pauta custa ~12 KB de HTML, porque a página traz um modal completo por
    pauta. Sem corte, um quadro de 100 pautas passa de 1 MB no celular.
    """

    def antiga(self):
        pauta = self.pauta("Resolvida ano passado", status=Pauta.Status.CONCLUIDA)
        # `atualizado_em` é auto_now: só um UPDATE direto envelhece o registro.
        Pauta.objects.filter(pk=pauta.pk).update(
            atualizado_em=timezone.now() - timedelta(
                days=DIAS_DE_CONCLUIDAS_NO_QUADRO + 5))
        return pauta

    def test_concluida_antiga_sai_do_quadro(self):
        self.antiga()
        self.assertNotIn("Resolvida ano passado", self.abrir())

    def test_concluida_recente_fica(self):
        self.pauta("Resolvida esta semana", status=Pauta.Status.CONCLUIDA)
        self.assertIn("Resolvida esta semana", self.abrir())

    def test_o_quadro_diz_quantas_escondeu(self):
        """Esconder em silêncio faria a pessoa achar que a pauta sumiu."""
        self.antiga()
        html = self.abrir()
        self.assertIn("+1 concluída há mais de", html)
        self.assertIn("?concluidas=todas", html)

    def test_historico_inteiro_sob_demanda(self):
        self.antiga()
        self.assertIn("Resolvida ano passado", self.abrir("?concluidas=todas"))

    def test_pauta_antiga_ainda_em_discussao_nao_some(self):
        """O corte é só para concluídas — assunto aberto nunca desaparece."""
        pauta = self.pauta("Arrastada há meses")
        Pauta.objects.filter(pk=pauta.pk).update(
            atualizado_em=timezone.now() - timedelta(days=365))
        self.assertIn("Arrastada há meses", self.abrir())


class DadosDoFiltroTest(BaseQuadro):
    """O card carrega em data-* tudo que o filtro do navegador precisa."""

    def test_card_leva_grupo_prioridade_e_marcadores(self):
        pauta = self.pauta("Comprar material",
                           prioridade=Pauta.Prioridade.ALTA)
        pauta.responsaveis.add(self.lider)
        html = self.abrir()

        self.assertIn('data-grupo="Lideranças"', html)
        self.assertIn('data-prioridade="ALTA"', html)
        self.assertIn('data-responsaveis="lider"', html)
        self.assertIn('data-minha="1"', html)
        self.assertIn('data-sem-ciencia="1"', html)

    def test_busca_alcanca_etiqueta_e_responsavel(self):
        """Nenhum dos dois aparece como texto no card — sem isso, some da busca."""
        pauta = self.pauta("Reunião de maio", etiquetas=["orçamento"])
        pauta.responsaveis.add(self.colega)
        html = self.abrir()

        self.assertIn("orçamento", html)
        self.assertIn("caio nunes", html)   # o texto de busca vem em minúsculas

    def test_filtro_so_oferece_grupo_que_esta_no_quadro(self):
        """Oferecer opção que não devolve resultado é pior que não oferecer."""
        self.pauta("Só do grupo Lideranças")
        html = self.abrir()

        self.assertIn('<option value="Lideranças">', html)
        self.assertNotIn('<option value="Conselho">', html)

    def test_filtro_so_oferece_responsavel_que_esta_no_quadro(self):
        pauta = self.pauta("Com responsável")
        pauta.responsaveis.add(self.colega)
        html = self.abrir()

        self.assertIn('<option value="colega">Caio Nunes</option>', html)
        self.assertNotIn('<option value="lider">', html)

    def test_quadro_vazio_nao_mostra_barra_de_filtro(self):
        """Filtro sobre nada só ocupa espaço e confunde."""
        html = self.abrir()
        self.assertNotIn("data-board-filters", html)
        self.assertIn("Seu quadro está livre", html)
