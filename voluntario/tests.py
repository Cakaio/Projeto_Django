import json

from django.test import TestCase
from django.urls import reverse

from sabado.models import Sabado

from .models import (
    Grupo, Voluntario, Ocorrencia, PresencaVoluntario, Regra,
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
