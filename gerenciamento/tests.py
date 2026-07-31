from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from voluntario.models import Grupo, Voluntario

from .models import CienciaPauta, ComentarioPauta, Pauta


class PautaTests(TestCase):
    def setUp(self):
        self.grupo = Grupo.objects.create(
            nome="Lideranças",
            regras=[{"areas": [], "cargos": ["LIDER"]}],
        )
        self.lider = Voluntario.objects.create_user(
            username="lider", password="teste123", area="VIOLETA", cargo="LIDER"
        )
        self.outro = Voluntario.objects.create_user(
            username="outro", password="teste123", area="SUPPLY"
        )
        self.pauta = Pauta.objects.create(
            titulo="Planejar evento",
            descricao="Definir responsáveis.",
            criado_por=self.outro,
            emitido_por_area=self.outro.area,
            ddl=timezone.now() + timedelta(days=3),
            grupo=self.grupo,
        )

    def test_usuario_ve_apenas_pautas_dos_grupos_atuais(self):
        self.client.force_login(self.lider)
        resposta = self.client.get(reverse("gerenciamento:pautas"))
        self.assertContains(resposta, "Planejar evento")

        self.lider.cargo = None
        self.lider.save(update_fields=["cargo"])
        resposta = self.client.get(reverse("gerenciamento:pautas"))
        self.assertNotContains(resposta, "Planejar evento")

    def test_criacao_registra_autor_e_area_atual(self):
        self.client.force_login(self.lider)
        resposta = self.client.post(reverse("gerenciamento:criar_pauta"), {
            "titulo": "Reunião",
            "descricao": "Alinhar o sábado.",
            "status": "A_FAZER",
            "ddl": (timezone.localtime() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "grupo": self.grupo.pk,
        })
        self.assertRedirects(resposta, reverse("gerenciamento:pautas"))
        criada = Pauta.objects.get(titulo="Reunião")
        self.assertEqual(criada.criado_por, self.lider)
        self.assertEqual(criada.emitido_por_area, "VIOLETA")

    def test_membro_pode_comentar(self):
        self.client.force_login(self.lider)
        self.client.post(
            reverse("gerenciamento:comentar_pauta", args=[self.pauta.pk]),
            {"texto": "Posso assumir essa parte."},
        )
        self.assertTrue(ComentarioPauta.objects.filter(
            pauta=self.pauta, autor=self.lider
        ).exists())

    def test_nao_membro_nao_pode_comentar(self):
        self.client.force_login(self.outro)
        self.client.post(
            reverse("gerenciamento:comentar_pauta", args=[self.pauta.pk]),
            {"texto": "Comentário indevido."},
        )
        self.assertFalse(ComentarioPauta.objects.filter(
            pauta=self.pauta, autor=self.outro
        ).exists())

    def test_membro_pode_tomar_ciencia_ocultar_e_restaurar(self):
        self.client.force_login(self.lider)
        self.client.post(
            reverse("gerenciamento:alternar_ciencia", args=[self.pauta.pk]),
            {"acao": "ocultar"},
        )
        estado = CienciaPauta.objects.get(pauta=self.pauta, voluntario=self.lider)
        self.assertTrue(estado.ocultada)
        self.assertNotContains(
            self.client.get(reverse("gerenciamento:pautas")), "Planejar evento"
        )
        self.assertContains(
            self.client.get(reverse("gerenciamento:pautas") + "?ocultas=1"),
            "Planejar evento",
        )

        self.client.post(
            reverse("gerenciamento:alternar_ciencia", args=[self.pauta.pk]),
            {"acao": "restaurar", "origem": "ocultas"},
        )
        estado.refresh_from_db()
        self.assertFalse(estado.ocultada)

    def test_area_emissora_pode_editar_status(self):
        self.client.force_login(self.outro)
        resposta = self.client.post(
            reverse("gerenciamento:editar_pauta", args=[self.pauta.pk]),
            {
                "titulo": self.pauta.titulo,
                "descricao": self.pauta.descricao,
                "status": "EM_EXECUCAO",
                "ddl": timezone.localtime(self.pauta.ddl).strftime("%Y-%m-%dT%H:%M"),
                "grupo": self.grupo.pk,
            },
        )
        self.assertRedirects(resposta, reverse("gerenciamento:minhas_pautas"))
        self.pauta.refresh_from_db()
        self.assertEqual(self.pauta.status, "EM_EXECUCAO")

    def test_usuario_de_outra_area_nao_pode_editar(self):
        self.client.force_login(self.lider)
        resposta = self.client.get(
            reverse("gerenciamento:editar_pauta", args=[self.pauta.pk])
        )
        self.assertRedirects(resposta, reverse("gerenciamento:minhas_pautas"))
