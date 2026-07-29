import json

from django.test import TestCase
from django.urls import reverse

from .models import Grupo, Voluntario


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
