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


class EscolherResponsaveisTest(BaseQuadro):
    """Vários responsáveis sempre existiram no modelo — a interface é que escondia.

    O formulário usava `<select multiple>` com a instrução "Use Ctrl (Windows)
    ou Command (macOS)". No celular isso é impraticável, e o PCF é PWA: o
    recurso existia e ninguém conseguia usar.
    """

    def abrir_formulario(self):
        from .views import criar_pauta

        pedido = self.factory.get("/gerenciamento/nova/")
        pedido.user = self.lider
        return criar_pauta(pedido).content.decode()

    def test_o_campo_virou_caixas_de_selecao(self):
        html = self.abrir_formulario()
        self.assertIn('name="responsaveis"', html)
        self.assertIn('type="checkbox"', html)

    def test_nao_sobrou_select_multiple_nem_instrucao_de_teclado(self):
        """A instrução de teclado era o sintoma: recurso que só o mouse alcança.

        Afirma o texto exato que existia, e não a palavra solta "Ctrl" — ela
        aparece legitimamente num comentário de CSS explicando esta mudança.
        """
        html = self.abrir_formulario()
        self.assertNotIn('<select name="responsaveis" multiple', html)
        self.assertNotIn("Use Ctrl (Windows) ou Command (macOS)", html)

    def test_tem_busca_para_achar_a_pessoa(self):
        """Com dezenas de voluntários, rolar a lista inteira não serve."""
        self.assertIn("data-pessoas-busca", self.abrir_formulario())

    def test_salva_mais_de_um_responsavel(self):
        """A prova que interessa: dois nomes marcados viram dois responsáveis."""
        from django.contrib.messages.storage.fallback import FallbackStorage

        from .views import criar_pauta

        pedido = self.factory.post("/gerenciamento/nova/", {
            "titulo": "Dividir a organização do evento",
            "descricao": "Duas pessoas tocam isso.",
            "prioridade": Pauta.Prioridade.MEDIA,
            "status": Pauta.Status.A_DISCUTIR,
            "prazo_ddl": (timezone.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"),
            "grupo": self.grupo.pk,
            "etiquetas_texto": "",
            "responsaveis": [str(self.lider.pk)],
        })
        pedido.user = self.lider
        pedido.session = {}
        pedido._messages = FallbackStorage(pedido)
        criar_pauta(pedido)

        criada = Pauta.objects.get(titulo="Dividir a organização do evento")
        self.assertEqual(list(criada.responsaveis.all()), [self.lider])


class DensidadeDoCardTest(BaseQuadro):
    """O card não pode gastar uma linha inteira repetindo o que a borda já diz."""

    def test_concluida_nao_cobra_ciencia_no_card(self):
        """Cobrar ciência de assunto encerrado é ruído — e contradizia o topo,
        que não conta concluídas como pendentes."""
        self.pauta("Encerrada", status=Pauta.Status.CONCLUIDA)
        html = self.abrir()

        self.assertIn("<strong>0</strong> esperando sua ciência", html)
        self.assertNotIn("Falta sua ciência", html)

    def test_pauta_aberta_sem_ciencia_avisa(self):
        self.pauta("Em aberto")
        self.assertIn("Falta sua ciência", self.abrir())

    def test_ciencia_registrada_nao_gasta_linha_no_card(self):
        """Registrada já aparece na cor da borda esquerda do card."""
        pauta = self.pauta("Já vista")
        CienciaPauta.objects.create(pauta=pauta, voluntario=self.lider)
        html = self.abrir()

        self.assertIn("is-acknowledged", html)
        self.assertNotIn("Sua ciência está registrada", html)
