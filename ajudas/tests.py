import datetime as dt
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from sabado.models import DisponibilidadeVoluntario, Sabado
from semanario.models import Semanario
from voluntario.models import LISTA_AREAS, Voluntario
from .models import Ajuda, EscalaAjuda, NecessidadeAjuda
from .selectors import (card_inicio, cobertura_necessidade, dados_quadro,
                        disponibilidades_confirmadas, historico_recente, sugerir_necessidades)
from .services import ConflitoEdicao, reabrir_escala, salvar_escala


class AjudasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sabado = Sabado.objects.create(data=timezone.localdate() + dt.timedelta(days=14), tema="Sábado de testes", descricao="Projeto")
        cls.triade = Voluntario.objects.create_user(username="triade", area="TRIADE")
        cls.azul = Voluntario.objects.create_user(username="caio", first_name="Caio", area="AZUL")
        cls.verde = Voluntario.objects.create_user(username="bia", first_name="Bia", area="VERDE")
        cls.ausente = Voluntario.objects.create_user(username="ausente", area="AZUL")
        DisponibilidadeVoluntario.objects.create(sabado=cls.sabado, voluntario=cls.azul, vai_ao_projeto=True, vai_de_carro=True)
        DisponibilidadeVoluntario.objects.create(sabado=cls.sabado, voluntario=cls.verde, vai_ao_projeto=True, vai_de_carro=False)
        DisponibilidadeVoluntario.objects.create(sabado=cls.sabado, voluntario=cls.ausente, vai_ao_projeto=False)

    def dados(self):
        return {"revisao": 0, "hora_inicio": "06:00", "hora_fim": "12:30",
                "necessidades": [
                    {"area": "AZUL", "hora_inicio": "09:00", "hora_fim": "11:00", "quantidade": 1},
                    {"area": "VERDE", "hora_inicio": "09:00", "hora_fim": "11:00", "quantidade": 2},
                    {"area": "SUPPLY", "hora_inicio": "06:00", "hora_fim": "07:00", "quantidade": 1},
                    {"area": "RECREACAO", "hora_inicio": "11:00", "hora_fim": "12:30", "quantidade": 1},
                ], "ajudas": [{"voluntario": self.azul.pk, "area_destino": "VERDE", "hora_inicio": "09:00", "hora_fim": "10:00"}]}

    def salvar(self, dados=None, publicar=False):
        return salvar_escala(usuario=self.triade, sabado_id=self.sabado.pk, dados=dados or self.dados(), publicar=publicar)

    def post(self, acao, dados=None, usuario=None):
        self.client.force_login(usuario or self.triade)
        return self.client.post(reverse(f"ajudas:{acao}", args=[self.sabado.pk]),
                                json.dumps(dados or self.dados()), content_type="application/json")

    def test_defaults_horario_preservam_sabados(self):
        self.assertEqual((self.sabado.hora_inicio, self.sabado.hora_fim), (dt.time(6), dt.time(12, 30)))

    def test_get_sugere_sem_gravar(self):
        self.client.force_login(self.triade)
        response = self.client.get(reverse("ajudas:organizar", args=[self.sabado.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(EscalaAjuda.objects.exists())
        quadro = response.context["quadro"]
        self.assertEqual(len(quadro["necessidades"]), 11)
        self.assertEqual(quadro["ajudas"], [])
        self.assertTrue(next(v for v in quadro["voluntarios"] if v["id"] == self.azul.pk)["vai_de_carro"])
        self.assertNotIn(self.ausente.pk, [v["id"] for v in quadro["voluntarios"]])

    def test_vagas_sao_extras_somadas_a_equipe_presente(self):
        Semanario.objects.create(data=self.sabado, sala="AZUL", vagas=4)
        sugestoes = sugerir_necessidades(self.sabado, disponibilidades_confirmadas(self.sabado))
        azul = next(n for n in sugestoes if n["area"] == "AZUL")
        self.assertEqual(azul["quantidade"], 5)
        self.assertIn("4 vagas extras", azul["sugestao"])

    def test_defaults_de_supply_recreacao_e_marketing(self):
        sugestoes = {n["area"]: n for n in sugerir_necessidades(self.sabado, [])}
        for area, inicio, fim in [("SUPPLY", "06:00", "07:00"), ("RECREACAO", "11:00", "12:30"), ("MARKETING", "09:00", "11:00")]:
            self.assertEqual((sugestoes[area]["hora_inicio"], sugestoes[area]["hora_fim"]), (inicio, fim))

    def test_defaults_cabem_no_sabado_atipico(self):
        self.sabado.hora_inicio, self.sabado.hora_fim = dt.time(10), dt.time(12)
        sugestoes = sugerir_necessidades(self.sabado, [])
        self.assertNotIn("SUPPLY", [n["area"] for n in sugestoes])
        for n in sugestoes:
            self.assertGreaterEqual(n["hora_inicio"], "10:00")
            self.assertLessEqual(n["hora_fim"], "12:00")

    def test_salvar_rascunho_nao_publica_e_proprios_nao_geram_ajuda(self):
        escala = self.salvar()
        self.assertEqual(escala.status, "RASCUNHO")
        self.assertEqual(escala.ajudas.count(), 1)
        self.assertIsNone(card_inicio(self.azul))

    def test_sugestoes_nao_reaparecem_apos_remover_todas(self):
        dados = self.dados()
        dados.update(ajudas=[], necessidades=[])
        self.salvar(dados)
        self.assertEqual(dados_quadro(self.sabado)["necessidades"], [])

    def test_quantidade_manual_nao_muda_quando_semanario_muda(self):
        sem = Semanario.objects.create(data=self.sabado, sala="AZUL", vagas=20)
        self.salvar()
        sem.vagas = 40
        sem.save()
        self.assertEqual(next(n for n in dados_quadro(self.sabado)["necessidades"] if n["area"] == "AZUL")["quantidade"], 1)

    def test_qualquer_area_pode_receber_necessidade(self):
        dados = self.dados()
        dados["necessidades"] = [{"area": area, "hora_inicio": "07:30", "hora_fim": "08:30", "quantidade": 2} for area, _ in LISTA_AREAS]
        dados["ajudas"] = [{"voluntario": self.azul.pk, "area_destino": "ADM/FIN", "hora_inicio": "07:30", "hora_fim": "08:30"}]
        self.assertEqual(self.salvar(dados).necessidades.count(), len(LISTA_AREAS))

    def test_multiplas_faixas_da_mesma_area_sem_sobreposicao(self):
        dados = self.dados()
        dados["necessidades"].append({"area": "RECREACAO", "hora_inicio": "07:00", "hora_fim": "08:00", "quantidade": 1})
        self.assertEqual(self.salvar(dados).necessidades.filter(area="RECREACAO").count(), 2)

    def test_necessidades_da_mesma_area_nao_sobrepoem(self):
        dados = self.dados()
        dados["necessidades"].append({"area": "VERDE", "hora_inicio": "10:00", "hora_fim": "12:00", "quantidade": 1})
        with self.assertRaises(ValidationError):
            self.salvar(dados)

    def test_mesma_pessoa_em_ajudas_diferentes_e_limites_contiguos(self):
        dados = self.dados()
        dados["ajudas"].extend([
            {"voluntario": self.azul.pk, "area_destino": "SUPPLY", "hora_inicio": "06:00", "hora_fim": "07:00"},
            {"voluntario": self.azul.pk, "area_destino": "VERDE", "hora_inicio": "10:00", "hora_fim": "11:00"},
            {"voluntario": self.azul.pk, "area_destino": "RECREACAO", "hora_inicio": "11:00", "hora_fim": "12:30"},
        ])
        self.assertEqual(self.salvar(dados, publicar=True).ajudas.count(), 4)

    def test_sobreposicao_parcial_completa_e_duplicada_bloqueadas(self):
        for inicio, fim in [("09:30", "10:30"), ("09:00", "11:00"), ("09:00", "10:00")]:
            with self.subTest(inicio=inicio, fim=fim):
                dados = self.dados()
                dados["ajudas"].append({"voluntario": self.azul.pk, "area_destino": "VERDE", "hora_inicio": inicio, "hora_fim": fim})
                with self.assertRaises(ValidationError):
                    self.salvar(dados, publicar=True)
                self.assertFalse(EscalaAjuda.objects.exists())

    def test_backend_recusa_voluntario_ausente_inexistente_e_sem_resposta(self):
        for pk in [self.ausente.pk, 999999, self.triade.pk]:
            with self.subTest(pk=pk):
                dados = self.dados()
                dados["ajudas"][0]["voluntario"] = pk
                self.assertEqual(self.post("publicar", dados).status_code, 400)

    def test_backend_recusa_inativo_e_desligado(self):
        for campo, valor in [("is_active", False), ("data_saida", timezone.localdate())]:
            with self.subTest(campo=campo):
                Voluntario.objects.filter(pk=self.azul.pk).update(**{campo: valor})
                self.assertEqual(self.post("salvar").status_code, 400)
                Voluntario.objects.filter(pk=self.azul.pk).update(is_active=True, data_saida=None)

    def test_presenca_em_outro_sabado_nao_habilita(self):
        outro = Sabado.objects.create(data=self.sabado.data + dt.timedelta(days=7), tema="Outro", descricao="Outro")
        DisponibilidadeVoluntario.objects.create(sabado=outro, voluntario=self.ausente, vai_ao_projeto=True)
        dados = self.dados()
        dados["ajudas"][0]["voluntario"] = self.ausente.pk
        with self.assertRaises(ValidationError):
            self.salvar(dados)

    def test_backend_recusa_propria_area(self):
        dados = self.dados()
        dados["ajudas"][0]["area_destino"] = "AZUL"
        self.assertEqual(self.post("salvar", dados).status_code, 400)

    def test_backend_recusa_horarios_invalidos_e_fora_do_sabado(self):
        for campo, valor in [("hora_inicio", "10:00"), ("hora_inicio", "05:00"), ("hora_fim", "13:00"), ("hora_fim", "25:00"), ("hora_inicio", ""), ("hora_inicio", "09:00:30")]:
            with self.subTest(campo=campo, valor=valor):
                dados = self.dados()
                dados["ajudas"][0][campo] = valor
                self.assertEqual(self.post("salvar", dados).status_code, 400)

    def test_backend_recusa_horarios_do_dia_e_necessidades_invalidos(self):
        for inicio, fim in [("12:30", "06:00"), ("06:00", "06:00")]:
            dados = self.dados()
            dados.update(hora_inicio=inicio, hora_fim=fim)
            self.assertEqual(self.post("salvar", dados).status_code, 400)
        dados = self.dados()
        dados["necessidades"][0]["hora_inicio"] = "05:00"
        self.assertEqual(self.post("salvar", dados).status_code, 400)

    def test_ajuda_precisa_caber_na_necessidade(self):
        dados = self.dados()
        dados["ajudas"][0]["hora_inicio"] = "08:00"
        with self.assertRaises(ValidationError):
            self.salvar(dados)

    def test_contagem_desconta_saida_e_retorna_na_hora_certa(self):
        escala = self.salvar()
        azul = escala.necessidades.get(area="AZUL")
        verde = escala.necessidades.get(area="VERDE")
        pessoas = [self.azul, self.verde]
        ajudas = list(escala.ajudas.all())
        segmentos = cobertura_necessidade(azul, pessoas, ajudas)
        self.assertEqual([(s["hora_inicio"], s["hora_fim"], s["total"]) for s in segmentos],
                         [(dt.time(9), dt.time(10), 0), (dt.time(10), dt.time(11), 1)])
        self.assertEqual([s["total"] for s in cobertura_necessidade(verde, pessoas, ajudas)], [2, 1])

    def test_presenca_parcial_nao_vira_cobertura_integral(self):
        escala = self.salvar()
        necessidade = escala.necessidades.get(area="VERDE")
        segmentos = cobertura_necessidade(necessidade, [self.azul, self.verde], list(escala.ajudas.all()))
        self.assertEqual([s["faltam"] for s in segmentos], [0, 1])
        self.assertEqual(segmentos[0]["extras"], [self.azul])

    def test_falta_ou_excesso_avisa_sem_impedir_publicacao(self):
        dados = self.dados()
        dados["necessidades"][0]["quantidade"] = 100
        dados["necessidades"][1]["quantidade"] = 0
        self.assertEqual(self.salvar(dados, publicar=True).status, "PUBLICADA")

    def test_edicao_do_conjunto_substitui_anterior_sem_falso_conflito(self):
        escala = self.salvar()
        dados = self.dados()
        dados["revisao"] = escala.revisao
        dados["ajudas"][0].update(hora_inicio="09:30", hora_fim="10:30")
        self.salvar(dados)
        self.assertEqual(Ajuda.objects.count(), 1)
        self.assertEqual(Ajuda.objects.get().hora_inicio, dt.time(9, 30))

    def test_erro_nao_apaga_escala_nem_altera_horario(self):
        escala = self.salvar()
        dados = self.dados()
        dados.update(revisao=escala.revisao, hora_inicio="05:00")
        dados["ajudas"][0]["voluntario"] = self.ausente.pk
        with self.assertRaises(ValidationError):
            self.salvar(dados, publicar=True)
        self.sabado.refresh_from_db()
        escala.refresh_from_db()
        self.assertEqual(self.sabado.hora_inicio, dt.time(6))
        self.assertEqual(escala.status, "RASCUNHO")
        self.assertEqual(escala.ajudas.count(), 1)
        self.assertEqual(escala.revisao, 1)

    def test_revisao_antiga_inclusive_duas_primeiras_edicoes_recusada(self):
        self.salvar()
        with self.assertRaises(ConflitoEdicao):
            self.salvar()
        self.assertEqual(self.post("salvar").status_code, 409)

    def test_publicada_exige_reabrir_e_oculta_ao_reabrir(self):
        escala = self.salvar(publicar=True)
        dados = self.dados()
        dados["revisao"] = escala.revisao
        self.assertEqual(self.post("salvar", dados).status_code, 409)
        resposta = self.post("reabrir", {"revisao": escala.revisao})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["quadro"]["status"], "RASCUNHO")
        self.assertIsNone(card_inicio(self.azul))
        self.assertEqual(Ajuda.objects.count(), 1)
        self.client.force_login(self.azul)
        self.assertEqual(self.client.get(reverse("ajudas:detalhe", args=[self.sabado.pk])).status_code, 404)

    def test_publicacao_revalida_presenca_e_pode_republicar_apos_correcao(self):
        escala = self.salvar()
        DisponibilidadeVoluntario.objects.filter(voluntario=self.azul, sabado=self.sabado).update(vai_ao_projeto=False)
        dados = self.dados()
        dados["revisao"] = escala.revisao
        self.assertEqual(self.post("publicar", dados).status_code, 400)
        quadro = dados_quadro(self.sabado)
        self.assertFalse(next(v for v in quadro["voluntarios"] if v["id"] == self.azul.pk)["apto"])
        dados["ajudas"] = []
        self.assertEqual(self.post("publicar", dados).status_code, 200)

    def test_permissao_exata_triade_inclusive_superuser(self):
        superuser = Voluntario.objects.create_superuser(username="admin", password="senha", area="AZUL")
        for usuario in [self.azul, superuser]:
            with self.subTest(usuario=usuario):
                self.client.force_login(usuario)
                self.assertEqual(self.client.get(reverse("ajudas:painel")).status_code, 403)
                self.assertEqual(self.client.get(reverse("ajudas:organizar", args=[self.sabado.pk])).status_code, 403)
                for acao in ["salvar", "publicar", "reabrir"]:
                    self.assertEqual(self.post(acao, usuario=usuario).status_code, 403)
                with self.assertRaises(PermissionDenied):
                    salvar_escala(usuario=usuario, sabado_id=self.sabado.pk, dados=self.dados())

    def test_anonimo_precisa_login_e_get_nao_muta(self):
        for nome in ["escala_publicada", "painel"]:
            self.assertEqual(self.client.get(reverse(f"ajudas:{nome}")).status_code, 302)
        self.client.force_login(self.triade)
        for nome in ["salvar", "publicar", "reabrir"]:
            self.assertEqual(self.client.get(reverse(f"ajudas:{nome}", args=[self.sabado.pk])).status_code, 405)
        self.assertFalse(EscalaAjuda.objects.exists())

    def test_csrf_obrigatorio(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.triade)
        url = reverse("ajudas:salvar", args=[self.sabado.pk])
        self.assertEqual(client.post(url, json.dumps(self.dados()), content_type="application/json").status_code, 403)

    def test_json_e_listas_malformados_nao_produzem_500(self):
        self.client.force_login(self.triade)
        url = reverse("ajudas:salvar", args=[self.sabado.pk])
        for dados in ["{", "null", "[]", "1", '{"revisao":0}', json.dumps({**self.dados(), "ajudas": [None]}), json.dumps({**self.dados(), "necessidades": {}})]:
            with self.subTest(dados=dados):
                self.assertEqual(self.client.post(url, dados, content_type="application/json").status_code, 400)

    def test_campos_json_com_tipos_errados_retornam_400(self):
        for campo, valor in [("hora_inicio", 900), ("hora_fim", {"hora": 10}), ("hora_inicio", ["09:00"]), ("voluntario", True)]:
            with self.subTest(campo=campo, valor=valor):
                dados = self.dados()
                dados["ajudas"][0][campo] = valor
                self.assertEqual(self.post("salvar", dados).status_code, 400)

    def test_model_full_clean_recusa_horarios_malformados_sem_type_error(self):
        escala = self.salvar()
        ajuda = Ajuda(escala=escala, voluntario=self.azul, area_destino="SUPPLY", hora_inicio="25:00", hora_fim=dt.time(7))
        with self.assertRaises(ValidationError):
            ajuda.full_clean()

    def test_rascunho_invisivel_e_publicada_visivel_sem_carro_ou_historico(self):
        escala = self.salvar()
        self.client.force_login(self.azul)
        url = reverse("ajudas:detalhe", args=[self.sabado.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        dados = self.dados()
        dados["revisao"] = escala.revisao
        self.salvar(dados, publicar=True)
        response = self.client.get(url)
        self.assertContains(response, "Caio")
        self.assertContains(response, "Você")
        self.assertNotContains(response, "Últimas ajudas")
        self.assertNotContains(response, "De carro")
        self.assertIn("no-store", response["Cache-Control"])

    def test_card_identifica_usuario_e_mantem_multiplas_ajudas_compactas(self):
        dados = self.dados()
        dados["ajudas"].append({"voluntario": self.azul.pk, "area_destino": "RECREACAO", "hora_inicio": "11:00", "hora_fim": "12:30"})
        self.salvar(dados, publicar=True)
        card = card_inicio(self.azul)
        self.assertEqual(card["principal"].area_destino, "VERDE")
        self.assertEqual(len(card["outras"]), 1)
        self.assertIsNone(card_inicio(self.verde))
        self.client.force_login(self.azul)
        response = self.client.get(reverse("inicio"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Suas ajudas"', count=1)
        self.assertContains(response, "+1 ajuda")

    def test_card_nao_pula_proxima_escala_sem_ajuda_do_usuario(self):
        self.salvar(publicar=True)
        anterior = Sabado.objects.create(data=self.sabado.data - dt.timedelta(days=7), tema="Mais próximo", descricao="Dia")
        EscalaAjuda.objects.create(sabado=anterior, status="PUBLICADA", publicada_em=timezone.now())
        self.assertIsNone(card_inicio(self.azul))

    def test_card_oculta_presenca_revogada(self):
        self.salvar(publicar=True)
        DisponibilidadeVoluntario.objects.filter(sabado=self.sabado, voluntario=self.azul).update(vai_ao_projeto=False)
        self.assertIsNone(card_inicio(self.azul))

    def test_historico_apenas_cinco_mais_recentes_publicadas_e_anteriores(self):
        hoje = timezone.localdate()
        for i in range(1, 8):
            sabado = Sabado.objects.create(data=hoje - dt.timedelta(days=7 * i), tema="Passado", descricao="Dia")
            escala = EscalaAjuda.objects.create(sabado=sabado, status="PUBLICADA" if i != 2 else "RASCUNHO", publicada_em=timezone.now() if i != 2 else None)
            DisponibilidadeVoluntario.objects.create(sabado=sabado, voluntario=self.azul)
            Ajuda.objects.create(escala=escala, voluntario=self.azul, area_destino="SUPPLY", hora_inicio=dt.time(6), hora_fim=dt.time(7))
        self.salvar(publicar=True)  # Futuro não vira histórico.
        historico = historico_recente(self.sabado, [self.azul.pk])[self.azul.pk]
        self.assertEqual(len(historico), 5)
        self.assertEqual(historico[0]["data"], (hoje - dt.timedelta(days=7)).strftime("%d/%m/%Y"))
        self.assertNotIn((hoje - dt.timedelta(days=14)).strftime("%d/%m/%Y"), [h["data"] for h in historico])

    def test_model_save_tambem_bloqueia_conflito_e_propria_area(self):
        escala = self.salvar()
        for area in ["AZUL", "VERDE"]:
            with self.subTest(area=area), self.assertRaises(ValidationError):
                Ajuda.objects.create(escala=escala, voluntario=self.azul, area_destino=area, hora_inicio=dt.time(9), hora_fim=dt.time(10))

    def test_model_save_recusa_inativo_ausente_e_foreign_key_invalida(self):
        escala = self.salvar()
        for voluntario_id in [self.ausente.pk, 999999]:
            with self.subTest(voluntario_id=voluntario_id), self.assertRaises(ValidationError):
                Ajuda.objects.create(escala=escala, voluntario_id=voluntario_id, area_destino="SUPPLY", hora_inicio=dt.time(6), hora_fim=dt.time(7))

    def test_admin_sabado_nao_encurta_periodo_sobre_ajudas(self):
        self.salvar()
        self.sabado.hora_inicio = dt.time(8)
        with self.assertRaises(ValidationError):
            self.sabado.clean()

    def test_pode_encurtar_dia_e_necessidades_na_mesma_edicao(self):
        escala = self.salvar()
        dados = self.dados()
        dados.update(revisao=escala.revisao, hora_inicio="08:00")
        dados["necessidades"] = [n for n in dados["necessidades"] if n["area"] != "SUPPLY"]
        self.salvar(dados)
        self.sabado.refresh_from_db()
        self.assertEqual(self.sabado.hora_inicio, dt.time(8))

    def test_constraint_banco_rejeita_periodo_invertido(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sabado.objects.filter(pk=self.sabado.pk).update(hora_inicio=dt.time(14))

    def test_consulta_vazia_e_painel_renderizam(self):
        self.client.force_login(self.triade)
        self.assertContains(self.client.get(reverse("ajudas:painel")), "Configurar ajudas")
        self.assertContains(self.client.get(reverse("ajudas:escala_publicada")), "quando for publicada")


class HorariosMigrationTests(TransactionTestCase):
    def test_sabado_antigo_recebe_defaults_sem_perder_dados(self):
        executor = MigrationExecutor(connection)
        atuais = executor.loader.graph.leaf_nodes()
        anterior = [("sabado", "0002_initial")]
        try:
            executor.migrate(anterior)
            SabadoAntigo = executor.loader.project_state(anterior).apps.get_model("sabado", "Sabado")
            registro = SabadoAntigo.objects.create(data=dt.date(2020, 9, 5), tema="Tema preservado", descricao="Descrição preservada")
            executor = MigrationExecutor(connection)
            executor.migrate(atuais)
            atualizado = Sabado.objects.get(pk=registro.pk)
            self.assertEqual(atualizado.tema, "Tema preservado")
            self.assertEqual(atualizado.descricao, "Descrição preservada")
            self.assertEqual((atualizado.hora_inicio, atualizado.hora_fim), (dt.time(6), dt.time(12, 30)))
        finally:
            MigrationExecutor(connection).migrate(atuais)
