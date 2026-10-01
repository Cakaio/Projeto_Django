import datetime as dt

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from sabado.models import DisponibilidadeVoluntario, Sabado
from voluntario.models import Voluntario
from .models import Ajuda, EscalaAjuda, NecessidadeAjuda
from .services import ConflitoEdicao, salvar_escala


class AjudaAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.triade = Voluntario.objects.create_user(username="gestora", area="TRIADE", is_staff=True)
        cls.voluntario = Voluntario.objects.create_user(username="caio", first_name="Caio", area="AZUL")
        cls.sabado = Sabado.objects.create(data=timezone.localdate(), tema="Admin", descricao="Teste")
        DisponibilidadeVoluntario.objects.create(sabado=cls.sabado, voluntario=cls.voluntario, vai_ao_projeto=True)
        cls.escala = EscalaAjuda.objects.create(sabado=cls.sabado)
        NecessidadeAjuda.objects.create(escala=cls.escala, area="VERDE", hora_inicio=dt.time(9), hora_fim=dt.time(11), quantidade=2)
        cls.ajuda = Ajuda.objects.create(escala=cls.escala, voluntario=cls.voluntario, area_destino="VERDE", hora_inicio=dt.time(9), hora_fim=dt.time(10))

    def setUp(self):
        self.client.force_login(self.triade)
        self.url = reverse("admin:ajudas_ajuda_change", args=[self.ajuda.pk])

    def dados(self, **mudancas):
        return {"voluntario": self.voluntario.pk, "area_destino": "VERDE", "hora_inicio": "09:15", "hora_fim": "10:15", "revisao_escala": 1, "_save": "Salvar", **mudancas}

    def test_tabelas_e_navegacao_dos_tres_models(self):
        for model in ["ajuda", "escalaajuda", "necessidadeajuda"]:
            self.assertEqual(self.client.get(reverse(f"admin:ajudas_{model}_changelist")).status_code, 200)
        tabela = self.client.get(reverse("admin:ajudas_ajuda_changelist"))
        for texto in ["Caio", "Azul", "Verde", "Rascunho"]:
            self.assertContains(tabela, texto)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        filtrada = self.client.get(reverse("admin:ajudas_ajuda_changelist"), {"escala__id__exact": self.escala.pk})
        self.assertContains(filtrada, "Caio")

    def test_edita_ajuda_e_atualiza_revisao_sem_trocar_sabado(self):
        outro = Sabado.objects.create(data=timezone.localdate() + dt.timedelta(days=7), tema="Outro", descricao="Outro")
        outra_escala = EscalaAjuda.objects.create(sabado=outro)
        resposta = self.client.post(self.url, self.dados(escala=outra_escala.pk))
        self.assertEqual(resposta.status_code, 302)
        self.ajuda.refresh_from_db()
        self.escala.refresh_from_db()
        self.assertEqual(self.ajuda.hora_inicio, dt.time(9, 15))
        self.assertEqual(self.ajuda.escala_id, self.escala.pk)
        self.assertEqual(self.escala.revisao, 2)

    def test_edicao_admin_invalida_aba_antiga_do_quadro(self):
        self.client.post(self.url, self.dados())
        with self.assertRaises(ConflitoEdicao):
            salvar_escala(usuario=self.triade, sabado_id=self.sabado.pk, dados={"revisao": 1, "ajudas": [], "necessidades": []})

    def test_revisao_obsoleta_ou_ausente_nao_sobrescreve(self):
        for revisao in [0, ""]:
            resposta = self.client.post(self.url, self.dados(revisao_escala=revisao))
            self.assertContains(resposta, "Outra pessoa alterou")
        self.ajuda.refresh_from_db()
        self.assertEqual(self.ajuda.hora_inicio, dt.time(9))

    def test_publicada_consulta_sem_edicao(self):
        EscalaAjuda.objects.filter(pk=self.escala.pk).update(status="PUBLICADA", publicada_em=timezone.now())
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, self.dados()).status_code, 403)

    def test_outras_areas_inclusive_superuser_nao_administram(self):
        usuario = Voluntario.objects.create_superuser(username="outro_admin", area="AZUL", password="teste")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("admin:ajudas_ajuda_changelist")).status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.dados()).status_code, 403)

    def test_conflito_bloqueado_sem_alterar_revisao(self):
        Ajuda.objects.create(escala=self.escala, voluntario=self.voluntario, area_destino="VERDE", hora_inicio=dt.time(10), hora_fim=dt.time(11))
        resposta = self.client.post(self.url, self.dados())
        self.assertContains(resposta, "já tem uma ajuda nesse horário")
        self.escala.refresh_from_db()
        self.ajuda.refresh_from_db()
        self.assertEqual(self.escala.revisao, 1)
        self.assertEqual(self.ajuda.hora_inicio, dt.time(9))

    def test_admin_recusa_fora_da_necessidade_e_propria_area(self):
        for alteracao in [{"hora_inicio": "08:00"}, {"hora_fim": "13:00"}, {"area_destino": "AZUL"}, {"hora_fim": "09:00"}]:
            with self.subTest(alteracao=alteracao):
                resposta = self.client.post(self.url, self.dados(**alteracao))
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.context["adminform"].form.errors)
        self.ajuda.refresh_from_db()
        self.assertEqual(self.ajuda.hora_inicio, dt.time(9))

    def test_presenca_revogada_bloqueia_edicao(self):
        DisponibilidadeVoluntario.objects.filter(voluntario=self.voluntario).update(vai_ao_projeto=False)
        resposta = self.client.post(self.url, self.dados())
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["adminform"].form.errors)
