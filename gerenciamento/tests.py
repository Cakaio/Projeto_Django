from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from voluntario.models import Grupo, Voluntario

from .models import CienciaPauta, Comentario, ComentarioPauta, Pauta, Reuniao


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
            prazo_ddl=timezone.now() + timedelta(days=3),
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

    def test_quadro_renderiza_colunas_modal_e_autocomplete(self):
        self.client.force_login(self.lider)
        resposta = self.client.get(reverse("gerenciamento:pautas"))

        self.assertContains(
            resposta,
            '<section class="pta-column" data-kanban-column',
            count=3,
        )
        self.assertContains(resposta, f'id="pautaModal{self.pauta.pk}"')
        self.assertContains(resposta, "data-mention-input")
        self.assertContains(resposta, "max-height: clamp(13rem, 35vh, 22rem)")
        self.assertContains(resposta, "Sua ciência está pendente")
        self.assertNotContains(resposta, "Ocultadas")
        self.assertNotContains(resposta, "Ciência realizada")
        self.assertNotContains(resposta, "Bloqueada")

    def test_criacao_registra_autor_e_area_atual(self):
        self.client.force_login(self.lider)
        resposta = self.client.post(reverse("gerenciamento:criar_pauta"), {
            "titulo": "Reunião",
            "descricao": "Alinhar o sábado.",
            "status": Pauta.Status.A_DISCUTIR,
            "prioridade": Pauta.Prioridade.ALTA,
            "prazo_ddl": (timezone.localtime() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "grupo": self.grupo.pk,
            "responsaveis": [self.lider.pk],
            "etiquetas_texto": "evento, urgente, evento",
        })
        self.assertRedirects(resposta, reverse("gerenciamento:pautas"))
        criada = Pauta.objects.get(titulo="Reunião")
        self.assertEqual(criada.criado_por, self.lider)
        self.assertEqual(criada.emitido_por_area, "VIOLETA")
        self.assertEqual(criada.prioridade, Pauta.Prioridade.ALTA)
        self.assertEqual(criada.etiquetas, ["evento", "urgente"])
        self.assertEqual(list(criada.responsaveis.all()), [self.lider])

    def test_membro_pode_comentar(self):
        self.client.force_login(self.lider)
        self.client.post(
            reverse("gerenciamento:comentar_pauta", args=[self.pauta.pk]),
            {"texto": "Posso assumir essa parte."},
        )
        self.assertTrue(ComentarioPauta.objects.filter(
            pauta=self.pauta, autor=self.lider
        ).exists())

    def test_comentario_identifica_mencoes_validas_sem_duplicar(self):
        self.client.force_login(self.lider)
        self.client.post(
            reverse("gerenciamento:comentar_pauta", args=[self.pauta.pk]),
            {"texto": "@outro veja isto. @OUTRO confirma com @inexistente?"},
        )
        comentario = Comentario.objects.get(pauta=self.pauta, autor=self.lider)
        self.assertEqual(list(comentario.mencoes.values_list("username", flat=True)), ["outro"])
        resposta = self.client.get(reverse("gerenciamento:pautas"))
        self.assertContains(resposta, 'data-mentioned-users="outro"')

    def test_nao_membro_nao_pode_comentar(self):
        self.client.force_login(self.outro)
        self.client.post(
            reverse("gerenciamento:comentar_pauta", args=[self.pauta.pk]),
            {"texto": "Comentário indevido."},
        )
        self.assertFalse(ComentarioPauta.objects.filter(
            pauta=self.pauta, autor=self.outro
        ).exists())

    def test_responsavel_continua_com_acesso_fora_do_grupo(self):
        self.pauta.responsaveis.add(self.outro)
        self.client.force_login(self.outro)

        resposta = self.client.get(reverse("gerenciamento:pautas"))

        self.assertContains(resposta, "Planejar evento")

    def test_ciencia_e_idempotente_e_nao_remove_pauta_do_quadro(self):
        self.client.force_login(self.lider)
        self.client.post(
            reverse("gerenciamento:registrar_ciencia", args=[self.pauta.pk]),
        )
        self.client.post(
            reverse("gerenciamento:registrar_ciencia", args=[self.pauta.pk]),
        )
        self.assertEqual(
            CienciaPauta.objects.filter(
                pauta=self.pauta, voluntario=self.lider
            ).count(),
            1,
        )
        self.assertContains(
            self.client.get(reverse("gerenciamento:pautas")),
            "Planejar evento",
        )

    def test_dar_ciencia_nao_oculta_o_card(self):
        self.client.force_login(self.lider)
        self.client.post(
            reverse("gerenciamento:registrar_ciencia", args=[self.pauta.pk]),
        )
        self.assertIn(self.lider, self.pauta.usuarios_ciencia.all())
        self.assertContains(
            self.client.get(reverse("gerenciamento:pautas")),
            "Planejar evento",
        )

    def test_area_emissora_pode_editar_status(self):
        self.client.force_login(self.outro)
        resposta = self.client.post(
            reverse("gerenciamento:editar_pauta", args=[self.pauta.pk]),
            {
                "titulo": self.pauta.titulo,
                "descricao": self.pauta.descricao,
                "status": Pauta.Status.EM_DISCUSSAO,
                "prioridade": self.pauta.prioridade,
                "prazo_ddl": timezone.localtime(self.pauta.prazo_ddl).strftime("%Y-%m-%dT%H:%M"),
                "grupo": self.grupo.pk,
                "etiquetas_texto": "",
            },
        )
        self.assertRedirects(resposta, reverse("gerenciamento:minhas_pautas"))
        self.pauta.refresh_from_db()
        self.assertEqual(self.pauta.status, Pauta.Status.EM_DISCUSSAO)

    def test_usuario_de_outra_area_nao_pode_editar(self):
        self.client.force_login(self.lider)
        resposta = self.client.get(
            reverse("gerenciamento:editar_pauta", args=[self.pauta.pk])
        )
        self.assertRedirects(resposta, reverse("gerenciamento:minhas_pautas"))

    def test_reuniao_agrupa_varias_pautas_do_mesmo_grupo(self):
        reuniao = Reuniao.objects.create(
            titulo="Alinhamento mensal",
            data_reuniao=timezone.now() + timedelta(days=5),
            grupo=self.grupo,
        )
        segunda = Pauta.objects.create(
            titulo="Segunda decisão",
            descricao="Outra conversa.",
            criado_por=self.outro,
            emitido_por_area=self.outro.area,
            prazo_ddl=timezone.now() + timedelta(days=6),
            grupo=self.grupo,
            reuniao=reuniao,
        )
        self.pauta.reuniao = reuniao
        self.pauta.save(update_fields=["reuniao"])

        self.assertCountEqual(reuniao.pautas.all(), [self.pauta, segunda])

    def test_status_disponiveis_sao_apenas_os_tres_novos(self):
        self.assertEqual(
            [codigo for codigo, _ in Pauta.Status.choices],
            ["A_DISCUTIR", "EM_DISCUSSAO", "CONCLUIDA"],
        )
        campos_ciencia = {campo.name for campo in CienciaPauta._meta.fields}
        self.assertNotIn("ocultada", campos_ciencia)
        self.assertNotIn("ocultada_em", campos_ciencia)

    def test_pauta_aceita_multiplos_responsaveis(self):
        segundo_lider = Voluntario.objects.create_user(
            username="segundo-lider",
            password="teste123",
            area="PROJETOS",
            cargo="LIDER",
        )
        self.pauta.responsaveis.add(self.lider, segundo_lider)

        self.assertCountEqual(
            self.pauta.responsaveis.all(),
            [self.lider, segundo_lider],
        )

    def test_tela_monta_reuniao_com_drag_drop_e_ordem(self):
        segunda = Pauta.objects.create(
            titulo="Definir orçamento",
            descricao="Validar os custos.",
            criado_por=self.outro,
            emitido_por_area=self.outro.area,
            prazo_ddl=timezone.now() + timedelta(days=4),
            grupo=self.grupo,
        )
        self.client.force_login(self.lider)
        pagina = self.client.get(reverse("gerenciamento:criar_reuniao"))
        self.assertContains(pagina, 'data-drop-zone="available"')
        self.assertContains(pagina, 'data-drop-zone="selected"')

        resposta = self.client.post(reverse("gerenciamento:criar_reuniao"), {
            "titulo": "Reunião de planejamento",
            "data_reuniao": (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            "descricao": "Fechar próximos passos.",
            "grupo": self.grupo.pk,
            "pautas_ids": f"{segunda.pk},{self.pauta.pk}",
        })

        reuniao = Reuniao.objects.get(titulo="Reunião de planejamento")
        self.assertRedirects(
            resposta,
            reverse("gerenciamento:painel_reuniao", args=[reuniao.pk]),
        )
        self.assertEqual(
            list(
                reuniao.pautas.order_by("ordem_reuniao")
                .values_list("pk", "ordem_reuniao")
            ),
            [(segunda.pk, 1), (self.pauta.pk, 2)],
        )

    def test_painel_reuniao_exibe_progresso_e_sincroniza_estado(self):
        reuniao = Reuniao.objects.create(
            titulo="Reunião ao vivo",
            data_reuniao=timezone.now(),
            grupo=self.grupo,
        )
        self.pauta.reuniao = reuniao
        self.pauta.ordem_reuniao = 1
        self.pauta.save(update_fields=["reuniao", "ordem_reuniao"])
        self.client.force_login(self.outro)

        painel = self.client.get(
            reverse("gerenciamento:painel_reuniao", args=[reuniao.pk])
        )
        self.assertContains(painel, 'data-meeting-panel')
        self.assertContains(painel, "Sincronização ativa")
        self.assertContains(painel, "Avançar para Em discussão")

        resposta = self.client.post(
            reverse("gerenciamento:atualizar_status", args=[self.pauta.pk]),
            {"status": Pauta.Status.EM_DISCUSSAO},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resposta.status_code, 200)
        estado = self.client.get(
            reverse("gerenciamento:estado_reuniao", args=[reuniao.pk])
        ).json()
        self.assertEqual(estado["pautas"][0]["status"], Pauta.Status.EM_DISCUSSAO)
        self.assertEqual(estado["pautas"][0]["proximo_status"], Pauta.Status.CONCLUIDA)

        fallback = self.client.post(
            reverse("gerenciamento:atualizar_status", args=[self.pauta.pk]),
            {
                "status": Pauta.Status.CONCLUIDA,
                "retorno": "painel_reuniao",
            },
        )
        self.assertRedirects(
            fallback,
            reverse("gerenciamento:painel_reuniao", args=[reuniao.pk]),
        )
        estado = self.client.get(
            reverse("gerenciamento:estado_reuniao", args=[reuniao.pk])
        ).json()
        self.assertEqual(estado["percentual"], 100)

    def test_usuario_sem_relacao_nao_acessa_painel_reuniao(self):
        reuniao = Reuniao.objects.create(
            titulo="Reunião restrita",
            data_reuniao=timezone.now(),
            grupo=self.grupo,
        )
        self.pauta.reuniao = reuniao
        self.pauta.save(update_fields=["reuniao"])
        intruso = Voluntario.objects.create_user(
            username="intruso",
            password="teste123",
            area="VIOLETA",
        )
        self.client.force_login(intruso)

        resposta = self.client.get(
            reverse("gerenciamento:painel_reuniao", args=[reuniao.pk])
        )

        self.assertEqual(resposta.status_code, 403)

    def test_area_emissora_move_card_por_endpoint(self):
        self.client.force_login(self.outro)
        resposta = self.client.post(
            reverse("gerenciamento:atualizar_status", args=[self.pauta.pk]),
            {"status": Pauta.Status.CONCLUIDA},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.json()["atrasada"])
        self.pauta.refresh_from_db()
        self.assertEqual(self.pauta.status, Pauta.Status.CONCLUIDA)

    def test_integrante_do_grupo_nao_move_card_de_outra_area(self):
        self.client.force_login(self.lider)
        resposta = self.client.post(
            reverse("gerenciamento:atualizar_status", args=[self.pauta.pk]),
            {"status": Pauta.Status.CONCLUIDA},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resposta.status_code, 403)
        self.pauta.refresh_from_db()
        self.assertEqual(self.pauta.status, Pauta.Status.A_DISCUTIR)

    def test_rota_canonicamente_montada_em_pautas(self):
        self.assertEqual(reverse("gerenciamento:pautas"), "/pautas/")
