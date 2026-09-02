import json

from django.test import TestCase
from django.urls import reverse

from sabado.models import Sabado

from .models import (
    Grupo, Voluntario, Ocorrencia, PresencaVoluntario, Regra, HistoricoLideranca,
    REGRA_FALTAS_CONSECUTIVAS,
)
from .views import verificar_faltas_e_gerar_alertas


class GrupoTests(TestCase):
    def setUp(self):
        self.gestor = Voluntario.objects.create_user(
            username="gestor", password="teste123", area="GESTAO_DE_TALENTOS"
        )
        self.lider_x = Voluntario.objects.create_user(
            username="lider-x", password="teste123", area="VIOLETA", cargo="LIDER"
        )
        self.leg = Voluntario.objects.create_user(
            username="leg", password="teste123", area="SUPPLY", cargo="LEG"
        )

    def test_integrantes_sao_calculados_por_regras_com_e_e_ou(self):
        grupo = Grupo.objects.create(nome="Gestão", regras=[
            {"areas": ["VIOLETA"], "cargos": ["LIDER"]},
            {"areas": [], "cargos": ["LEG"]},
        ])
        self.assertQuerySetEqual(
            grupo.voluntarios(), [self.leg, self.lider_x],
            transform=lambda item: item, ordered=False,
        )

    def test_voluntario_muda_de_grupo_automaticamente_ao_mudar_cargo(self):
        grupo = Grupo.objects.create(
            nome="Lideranças", regras=[{"areas": [], "cargos": ["LIDER"]}]
        )
        self.assertIn(self.lider_x, grupo.voluntarios())
        self.lider_x.cargo = None
        self.lider_x.save(update_fields=["cargo"])
        self.assertNotIn(self.lider_x, grupo.voluntarios())

    def test_gestor_pode_criar_grupo_pela_tela(self):
        self.client.force_login(self.gestor)
        resposta = self.client.post(reverse("voluntario:criar_grupo"), {
            "nome": "Pimentão",
            "regras": json.dumps([{"areas": ["VIOLETA", "AZUL"], "cargos": []}]),
        })
        self.assertRedirects(resposta, reverse("voluntario:grupos"))
        self.assertTrue(Grupo.objects.filter(nome="Pimentão").exists())

    def test_regra_vazia_nao_e_aceita(self):
        self.client.force_login(self.gestor)
        resposta = self.client.post(reverse("voluntario:criar_grupo"), {
            "nome": "Inválido",
            "regras": json.dumps([{"areas": [], "cargos": []}]),
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Grupo.objects.filter(nome="Inválido").exists())

    def test_tela_lista_grupo_e_integrantes(self):
        Grupo.objects.create(
            nome="Lideranças", regras=[{"areas": [], "cargos": ["LIDER"]}]
        )
        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("voluntario:grupos"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Lideranças")
        self.assertContains(resposta, "lider-x")

# Create your tests here.


class AlertaAutomaticoDeFaltaTests(TestCase):
    """A régua do alerta automático: 3 faltas SEGUIDAS, e uma regra só.

    Os dois pontos que a liderança reclamou: o alerta chegava com o texto de
    outra regra, e chegava para quem não tinha faltado 3 sábados seguidos.
    """

    def setUp(self):
        from datetime import date
        self.voluntario = Voluntario.objects.create_user(
            username="faltante", password="teste123", area="VIOLETA",
        )
        # Seis sábados quinzenais, do mais antigo para o mais recente.
        self.sabados = [
            Sabado.objects.create(data=date(2026, 3, dia), tema=f"T{dia}", descricao="d")
            for dia in (7, 14, 21, 28)
        ]

    def _registrar(self, indice, presenca):
        PresencaVoluntario.objects.create(
            voluntario=self.voluntario, data=self.sabados[indice], presenca=presenca,
        )

    def _alertas(self):
        return Ocorrencia.objects.filter(
            advertido=self.voluntario, tipo='ALERTA', automatico=True,
        )

    def test_tres_faltas_seguidas_geram_alerta_com_a_regra_de_faltas_consecutivas(self):
        for i in (1, 2, 3):
            self._registrar(i, 'AUSENTE')

        verificar_faltas_e_gerar_alertas(
            self.voluntario, self.sabados[3], None, notificar=False,
        )

        alerta = self._alertas().get()
        self.assertEqual(alerta.regra, REGRA_FALTAS_CONSECUTIVAS)
        # O texto da regra tem que falar de 3 sábados seguidos, e não de
        # julgamento do líder — era exatamente esse o desencaixe reclamado.
        self.assertIn('três sábados seguidos', Ocorrencia.REGRAS_DICT[alerta.regra])

    def test_tres_faltas_espalhadas_nao_geram_alerta(self):
        """Faltou, veio, faltou, veio... não é sumiço: não pode virar alerta."""
        self._registrar(0, 'AUSENTE')
        self._registrar(1, 'PRESENTE')
        self._registrar(2, 'AUSENTE')
        self._registrar(3, 'AUSENTE')

        verificar_faltas_e_gerar_alertas(
            self.voluntario, self.sabados[3], None, notificar=False,
        )

        self.assertFalse(self._alertas().exists())

    def test_falta_justificada_reinicia_a_sequencia(self):
        self._registrar(0, 'AUSENTE')
        self._registrar(1, 'AUSENTE')
        self._registrar(2, 'JUSTIFICADA')
        self._registrar(3, 'AUSENTE')

        verificar_faltas_e_gerar_alertas(
            self.voluntario, self.sabados[3], None, notificar=False,
        )

        self.assertFalse(self._alertas().exists())

    def test_nao_duplica_alerta_na_mesma_sequencia(self):
        for i in (1, 2, 3):
            self._registrar(i, 'AUSENTE')

        for _ in range(3):
            verificar_faltas_e_gerar_alertas(
                self.voluntario, self.sabados[3], None, notificar=False,
            )

        self.assertEqual(self._alertas().count(), 1)

    def test_comando_retroativo_usa_a_mesma_regua(self):
        """O comando tinha régua própria (faltas totais, regra AL2). Não tem mais."""
        from io import StringIO
        from django.core.management import call_command

        self._registrar(0, 'AUSENTE')
        self._registrar(1, 'PRESENTE')
        self._registrar(2, 'AUSENTE')
        self._registrar(3, 'AUSENTE')

        call_command('sync_alertas_faltas', stdout=StringIO())
        self.assertFalse(self._alertas().exists())

        # Agora sim, três seguidas: o mesmo comando passa a alertar — com a regra certa.
        PresencaVoluntario.objects.filter(data=self.sabados[1]).update(presenca='AUSENTE')
        call_command('sync_alertas_faltas', stdout=StringIO())

        self.assertEqual(self._alertas().get().regra, REGRA_FALTAS_CONSECUTIVAS)

    def test_a_regra_esta_no_catalogo_e_disponivel_para_aplicar(self):
        """Não basta o código existir na lista fixa: a regra tem que estar no
        catálogo, senão não aparece no painel nem no admin da Tríade."""
        regra = Regra.objects.get(codigo=REGRA_FALTAS_CONSECUTIVAS)
        self.assertEqual(regra.tipo, 'ALERTA')
        self.assertTrue(regra.ativo)
        self.assertIn('três sábados seguidos', regra.descricao)
        # O painel lista por `ativo=True` — é essa consulta que a torna aplicável.
        self.assertIn(regra, Regra.objects.filter(ativo=True))

    def test_foi_um_sabado_e_faltou_dois_nao_aplica(self):
        """Compareceu, depois faltou 2 seguidos: são 2, não 3. Nada acontece."""
        self._registrar(0, 'PRESENTE')
        self._registrar(1, 'AUSENTE')
        self._registrar(2, 'AUSENTE')

        verificar_faltas_e_gerar_alertas(
            self.voluntario, self.sabados[2], None, notificar=False,
        )

        self.assertFalse(self._alertas().exists())

    def test_foi_um_sabado_e_faltou_tres_seguidos_aplica(self):
        """Compareceu, depois sumiu por 3 sábados: é o caso da regra."""
        self._registrar(0, 'PRESENTE')
        for i in (1, 2, 3):
            self._registrar(i, 'AUSENTE')

        verificar_faltas_e_gerar_alertas(
            self.voluntario, self.sabados[3], None, notificar=False,
        )

        self.assertEqual(self._alertas().get().regra, REGRA_FALTAS_CONSECUTIVAS)

    def test_a_terceira_falta_aplica_no_momento_em_que_e_registrada(self):
        """A presença anterior não 'protege': o que conta é a sequência atual."""
        self._registrar(0, 'PRESENTE')
        self._registrar(1, 'AUSENTE')
        self._registrar(2, 'AUSENTE')
        verificar_faltas_e_gerar_alertas(
            self.voluntario, self.sabados[2], None, notificar=False,
        )
        self.assertFalse(self._alertas().exists())  # ainda 2

        self._registrar(3, 'AUSENTE')
        verificar_faltas_e_gerar_alertas(
            self.voluntario, self.sabados[3], None, notificar=False,
        )
        self.assertEqual(self._alertas().count(), 1)  # virou 3


class VoluntarioDesativadoSomeDasListagensTest(TestCase):
    """"Desativar" tem dois significados no sistema, e os dois somem das telas.

    Antes cada tela escolhia um critério: umas filtravam `is_active`, outras
    `data_saida`, outras nada. Quem era desativado por um jeito continuava
    aparecendo nas telas que olhavam o outro.
    """

    def setUp(self):
        import datetime
        self.ativo = Voluntario.objects.create_user(
            username="ativo", password="x", area="VIOLETA", first_name="Ana",
        )
        self.sem_login = Voluntario.objects.create_user(
            username="sem-login", password="x", area="VIOLETA", first_name="Bia",
            is_active=False,
        )
        self.desligado = Voluntario.objects.create_user(
            username="desligado", password="x", area="VIOLETA", first_name="Caio",
            data_saida=datetime.date(2026, 1, 10),
        )

    def test_ativos_exclui_os_dois_jeitos_de_desativar(self):
        self.assertQuerySetEqual(
            Voluntario.objects.ativos(), [self.ativo], transform=lambda x: x,
        )

    def test_a_listagem_de_voluntarios_nao_traz_nenhum_dos_dois(self):
        from .views import ListaVoluntario
        self.assertQuerySetEqual(
            ListaVoluntario().get_queryset(), [self.ativo], transform=lambda x: x,
        )

    def test_admin_continua_enxergando_todos(self):
        self.assertEqual(Voluntario.objects.count(), 3)


class HistoricoLideresTest(TestCase):
    """A tela é uma cadeia de sucessão: foto, área, ano, descrição, com setas.

    Renderiza pelo RequestFactory porque o test client quebra ao instrumentar
    template no Python 3.14 (copy() de Context) — o defeito é do client, não da
    view, e a página precisa ser exercida de verdade.
    """

    def setUp(self):
        import datetime
        from django.test import RequestFactory
        from .models import HistoricoLideranca

        self.fabrica = RequestFactory()
        self.admin = Voluntario.objects.create_superuser(
            username='chefe', password='x', email='c@pcf.org',
        )
        self.primeira = Voluntario.objects.create_user(
            username='ana', password='x', area='VIOLETA',
            first_name='Ana', last_name='Prado',
        )
        self.segunda = Voluntario.objects.create_user(
            username='bruno', password='x', area='VIOLETA',
            first_name='Bruno', last_name='Lima',
        )
        HistoricoLideranca.objects.create(
            voluntario=self.segunda, cargo='Líder de Sala', area='VIOLETA',
            data_inicio=datetime.date(2025, 2, 1),
        )
        HistoricoLideranca.objects.create(
            voluntario=self.primeira, cargo='Líder de Sala', area='VIOLETA',
            data_inicio=datetime.date(2023, 2, 1), data_fim=datetime.date(2024, 12, 1),
            descricao='Montou a sala do zero.',
        )

    def _renderizar(self):
        from .views import historico_lideres
        requisicao = self.fabrica.get('/voluntario/lideres/')
        requisicao.user = self.admin
        return historico_lideres(requisicao).content.decode()

    def test_a_sucessao_sai_do_mais_antigo_para_o_mais_novo(self):
        """A seta liga quem veio antes a quem veio depois: inverter faz ela mentir."""
        html = self._renderizar()
        self.assertLess(html.index('Ana Prado'), html.index('Bruno Lima'))

    def test_mostra_ano_foto_e_descricao_da_passagem(self):
        html = self._renderizar()
        self.assertIn('2023–2024', html)      # gestão encerrada
        self.assertIn('2025 · atual', html)   # quem está no cargo
        self.assertIn('Montou a sala do zero.', html)
        self.assertIn('hl-foto-vazia', html)  # sem foto cadastrada, cai no placeholder

    def test_tem_uma_seta_a_menos_que_lideres(self):
        """Duas pessoas, uma seta. Seta sobrando apontaria para o vazio."""
        html = self._renderizar()
        self.assertEqual(html.count('class="hl-seta"'), 1)

    def test_lider_desligado_do_projeto_continua_no_historico(self):
        """Arquivar alguém não pode apagar que essa pessoa liderou uma área."""
        import datetime
        self.primeira.data_saida = datetime.date(2025, 1, 10)
        self.primeira.is_active = False
        self.primeira.save()

        html = self._renderizar()
        self.assertIn('Ana Prado', html)


class LiderSemFichaTest(TestCase):
    """Boa parte de quem liderou saiu antes de existir site e nunca terá login.

    Exigir ficha deixaria essas gestões fora da história — que é exatamente o
    que esta tela existe para contar.
    """

    def setUp(self):
        import datetime
        from django.test import RequestFactory
        from .models import HistoricoLideranca

        self.fabrica = RequestFactory()
        self.admin = Voluntario.objects.create_superuser(
            username='chefe2', password='x', email='c2@pcf.org')
        self.registro = HistoricoLideranca.objects.create(
            nome_avulso='Tia Zefa', cargo='Líder de Sala', area='VERDE',
            data_inicio=datetime.date(2011, 3, 1), data_fim=datetime.date(2012, 12, 1),
            descricao='Abriu a sala no salão da igreja.',
        )

    def _renderizar(self, **filtros):
        from .views import historico_lideres
        requisicao = self.fabrica.get('/voluntario/lideres/', filtros)
        requisicao.user = self.admin
        return historico_lideres(requisicao).content.decode()

    def test_aparece_na_tela_sem_ter_conta(self):
        html = self._renderizar()
        self.assertIn('Tia Zefa', html)
        self.assertIn('Abriu a sala no salão da igreja.', html)

    def test_e_marcado_como_sem_ficha(self):
        self.assertIn('sem ficha no sistema', self._renderizar())

    def test_nao_vira_link_de_trajetoria(self):
        """Link que não leva a nada é pior que texto: sem ficha não há trajetória."""
        self.assertNotIn('?pessoa=None', self._renderizar())

    def test_de_quem_usa_o_nome_digitado(self):
        self.assertEqual(self.registro.de_quem, 'Tia Zefa')

    def test_exige_ficha_ou_nome(self):
        import datetime
        from django.core.exceptions import ValidationError
        from .models import HistoricoLideranca
        registro = HistoricoLideranca(cargo='Líder', area='AZUL',
                                      data_inicio=datetime.date(2020, 1, 1))
        with self.assertRaises(ValidationError):
            registro.full_clean()

    def test_a_ficha_tem_prioridade_sobre_o_nome_digitado(self):
        import datetime
        from .models import HistoricoLideranca
        pessoa = Voluntario.objects.create_user(
            username='rita', password='x', area='AZUL',
            first_name='Rita', last_name='Alves')
        registro = HistoricoLideranca(
            voluntario=pessoa, nome_avulso='errado', cargo='Líder',
            data_inicio=datetime.date(2020, 1, 1))
        self.assertEqual(registro.de_quem, 'Rita Alves')


class OrdemEFiltrosDoHistoricoTest(TestCase):

    def setUp(self):
        import datetime
        from django.test import RequestFactory
        from .models import HistoricoLideranca

        self.fabrica = RequestFactory()
        self.admin = Voluntario.objects.create_superuser(
            username='chefe3', password='x', email='c3@pcf.org')
        self.presidente = Voluntario.objects.create_user(
            username='duda', password='x', area='TRIADE',
            first_name='Duda', last_name='Nunes')

        HistoricoLideranca.objects.create(
            voluntario=self.presidente, cargo='Presidente', area='TRIADE',
            data_inicio=datetime.date(2026, 1, 1))
        HistoricoLideranca.objects.create(
            nome_avulso='Alguém do Violeta', cargo='Líder de Sala', area='VIOLETA',
            data_inicio=datetime.date(2023, 1, 1), data_fim=datetime.date(2023, 12, 1))
        HistoricoLideranca.objects.create(
            voluntario=self.presidente, cargo='Líder de Sala', area='AZUL',
            data_inicio=datetime.date(2024, 1, 1), data_fim=datetime.date(2024, 12, 1))

    def _renderizar(self, **filtros):
        from .views import historico_lideres
        requisicao = self.fabrica.get('/voluntario/lideres/', filtros)
        requisicao.user = self.admin
        return historico_lideres(requisicao).content.decode()

    def test_a_triade_vem_sempre_primeiro(self):
        """No LISTA_AREAS a Tríade é a ÚLTIMA; ordenar por ela a jogaria para o
        fim da página. A liderança pediu o contrário."""
        html = self._renderizar()
        self.assertLess(html.index('Tríade'), html.index('Violeta'))

    def test_filtro_por_area_deixa_so_ela(self):
        html = self._renderizar(area='VIOLETA')
        self.assertIn('Alguém do Violeta', html)
        self.assertNotIn('Presidente', html)

    def test_busca_acha_por_nome_digitado(self):
        html = self._renderizar(q='Violeta')
        self.assertIn('Alguém do Violeta', html)

    def test_busca_acha_por_cargo(self):
        html = self._renderizar(q='Presidente')
        self.assertIn('Duda Nunes', html)

    def test_trajetoria_mostra_a_pessoa_atravessando_as_areas(self):
        html = self._renderizar(pessoa=self.presidente.pk)
        self.assertIn('hl-traj', html)
        self.assertIn('2 gestões no projeto', html)

    def test_trajetoria_ignora_o_filtro_de_area(self):
        """Quem clica num nome quer a vida inteira daquela pessoa, não a
        interseção com o filtro que estava na tela."""
        html = self._renderizar(pessoa=self.presidente.pk, area='AZUL')
        self.assertIn('2 gestões no projeto', html)

    def test_pessoa_inexistente_nao_estoura(self):
        self.assertIn('Histórico de Líderes', self._renderizar(pessoa='99999'))

    def test_pessoa_nao_numerica_nao_estoura(self):
        """`?pessoa=abc` chegaria no queryset como int() e viraria erro 500."""
        self.assertIn('Histórico de Líderes', self._renderizar(pessoa='abc'))

    def test_o_select_de_areas_nao_encolhe_com_o_filtro(self):
        """Encolher a lista conforme se filtra deixaria a pessoa sem como voltar
        para outra área."""
        html = self._renderizar(area='VIOLETA')
        self.assertIn('value="TRIADE"', html)
