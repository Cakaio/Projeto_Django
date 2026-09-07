from datetime import timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from voluntario.models import Grupo, Voluntario

from .forms import MateriaisPautaForm
from .models import CienciaPauta, ComentarioPauta, MaterialPauta, NotificacaoMencaoPauta, Pauta


class DetalhesPautaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grupo = Grupo.objects.create(nome="Equipe", regras=[{"areas": ["VIOLETA"], "cargos": []}])
        cls.autor = Voluntario.objects.create_user(username="autor", area="VIOLETA")
        cls.membro = Voluntario.objects.create_user(username="ana", first_name="Ana", last_name="Silva", area="VIOLETA")
        cls.fora = Voluntario.objects.create_user(username="fora", area="SUPPLY")
        cls.pauta = Pauta.objects.create(titulo="Decisão", descricao="Contexto", grupo=cls.grupo,
            criado_por=cls.autor, emitido_por_area="VIOLETA", prazo_ddl=timezone.now() + timedelta(days=3))

    def setUp(self):
        self.client.force_login(self.autor)
        pasta = TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        configuracao = override_settings(MEDIA_ROOT=pasta.name)
        configuracao.enable()
        self.addCleanup(configuracao.disable)

    def test_ciencias_paginadas_busca_e_contador_acima_de_cem(self):
        pessoas = [Voluntario(username=f"pessoa{i:03}", area="VIOLETA") for i in range(105)]
        Voluntario.objects.bulk_create(pessoas)
        CienciaPauta.objects.bulk_create([CienciaPauta(pauta=self.pauta, voluntario=pessoa) for pessoa in pessoas])
        CienciaPauta.objects.create(pauta=self.pauta, voluntario=self.membro)
        url = reverse("gerenciamento:ciencias_pauta", args=[self.pauta.pk])
        dados = self.client.get(url).json()
        self.assertEqual(dados["total"], 106)
        self.assertEqual(len(dados["pessoas"]), 20)
        self.assertEqual(dados["proxima"], 2)
        self.assertEqual(len(self.client.get(url, {"page": 6}).json()["pessoas"]), 6)
        self.assertEqual(self.client.get(url, {"q": "Ana Silva"}).json()["pessoas"][0]["username"], "ana")
        self.assertEqual(self.client.get(url, {"q": "inexistente"}).json()["total"], 0)
        self.assertContains(self.client.get(reverse("gerenciamento:pautas")), "106 pessoas com ciência")
        self.client.force_login(self.fora)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_varios_documentos_e_links_no_modal_e_download(self):
        url = reverse("gerenciamento:adicionar_materiais", args=[self.pauta.pk])
        resposta = self.client.post(url, {
            "documentos": [SimpleUploadedFile("ata.pdf", b"%PDF-1.4 conteudo"), SimpleUploadedFile("dados.csv", b"nome,total\nAna,2")],
            "links": "https://example.org/ata\nhttps://example.org/ata\nhttps://example.org/dados",
        }, follow=True)
        self.assertEqual(self.pauta.materiais.count(), 4)
        self.assertContains(resposta, "ata.pdf")
        self.assertContains(resposta, 'rel="noopener noreferrer"')
        documento = self.pauta.materiais.get(nome="ata.pdf")
        download = self.client.get(reverse("gerenciamento:baixar_material", args=[documento.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertIn("attachment", download["Content-Disposition"])
        self.assertEqual(b"".join(download.streaming_content), b"%PDF-1.4 conteudo")
        download.close()
        self.client.force_login(self.fora)
        self.assertEqual(self.client.get(reverse("gerenciamento:baixar_material", args=[documento.pk])).status_code, 403)
        self.assertEqual(self.client.post(url, {"links": "https://example.org"}).status_code, 404)

    def test_membro_sem_permissao_de_edicao_nao_anexa(self):
        self.pauta.emitido_por_area = "SUPPLY"
        self.pauta.save()
        url = reverse("gerenciamento:adicionar_materiais", args=[self.pauta.pk])
        self.assertEqual(self.client.post(url, {"links": "https://example.org"}).status_code, 403)
        self.pauta.responsaveis.add(self.autor)
        self.assertEqual(self.client.post(url, {"links": "https://example.org"}).status_code, 302)

    def test_upload_invalido_nao_salva_parcialmente_e_preserva_modal(self):
        resposta = self.client.post(reverse("gerenciamento:adicionar_materiais", args=[self.pauta.pk]), {
            "documentos": [SimpleUploadedFile("ok.pdf", b"pdf"), SimpleUploadedFile("ruim.html", b"html")],
            "links": "https://example.org/documento",
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.pauta.materiais.count(), 0)
        self.assertEqual(resposta.context["pauta_aberta_id"], str(self.pauta.pk))
        self.assertContains(resposta, "https://example.org/documento")
        self.assertTrue(resposta.context["materiais_form"].errors)

    def test_limites_e_links_perigosos(self):
        for link in ["javascript:alert(1)", "ftp://example.org/file", "data:text/html,teste"]:
            self.assertFalse(MateriaisPautaForm({"links": link}).is_valid())
        arquivo = SimpleUploadedFile("grande.pdf", b"pdf")
        arquivo.size = 10 * 1024 * 1024 + 1
        self.assertFalse(MateriaisPautaForm({}, {"documentos": [arquivo]}).is_valid())
        self.assertFalse(MateriaisPautaForm({}, {"documentos": [SimpleUploadedFile("ata.pdf", b"pdf") for _ in range(11)]}).is_valid())

    def test_criar_e_editar_com_materiais(self):
        dados = {"titulo": "Nova pauta", "descricao": "Descrição", "status": Pauta.Status.A_DISCUTIR,
            "prioridade": Pauta.Prioridade.MEDIA, "grupo": self.grupo.pk,
            "prazo_ddl": timezone.localtime(self.pauta.prazo_ddl).strftime("%Y-%m-%dT%H:%M"),
            "documentos": SimpleUploadedFile("inicial.pdf", b"pdf"), "links": "https://example.org/inicial"}
        self.assertEqual(self.client.post(reverse("gerenciamento:criar_pauta"), dados).status_code, 302)
        criada = Pauta.objects.get(titulo="Nova pauta")
        self.assertEqual(criada.materiais.count(), 2)
        dados.pop("documentos")
        dados["links"] = "https://example.org/novo"
        self.assertEqual(self.client.post(reverse("gerenciamento:editar_pauta", args=[criada.pk]), dados).status_code, 302)
        self.assertEqual(criada.materiais.count(), 3)

    @patch("gerenciamento.services.enviar_push_async")
    def test_mencao_persistente_push_apos_commit_e_sem_duplicacao(self, push):
        with self.captureOnCommitCallbacks(execute=True):
            comentario = ComentarioPauta.objects.create(pauta=self.pauta, autor=self.autor, texto="@ana @ANA @autor @fora @inexistente")
            self.assertFalse(push.called)
        self.assertEqual(NotificacaoMencaoPauta.objects.count(), 1)
        notificacao = NotificacaoMencaoPauta.objects.get()
        self.assertEqual(notificacao.destinatario, self.membro)
        push.assert_called_once()
        self.assertIn(f"comentario={comentario.pk}", push.call_args.kwargs["url"])
        with self.captureOnCommitCallbacks(execute=True):
            comentario.save()
        self.assertEqual(push.call_count, 1)
        self.client.force_login(self.membro)
        resposta = self.client.get(reverse("gerenciamento:mencoes"))
        self.assertContains(resposta, "Nova menção")
        self.assertContains(resposta, 'data-mention-badge')
        self.assertContains(resposta, f"comentario={comentario.pk}")

    def test_ler_mencoes_exige_post_e_so_marca_do_usuario(self):
        comentario = ComentarioPauta.objects.create(pauta=self.pauta, autor=self.autor, texto="@ana")
        url = reverse("gerenciamento:ler_mencoes", args=[self.pauta.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        self.assertIsNone(NotificacaoMencaoPauta.objects.get(comentario=comentario).lida_em)
        self.client.force_login(self.membro)
        dados = self.client.post(url).json()
        self.assertEqual(dados["nao_lidas"], 0)
        self.assertIsNotNone(NotificacaoMencaoPauta.objects.get(comentario=comentario).lida_em)

    def test_mencoes_nao_expoem_pauta_apos_perda_de_acesso(self):
        ComentarioPauta.objects.create(pauta=self.pauta, autor=self.autor, texto="@ana")
        self.membro.area = "SUPPLY"
        self.membro.save(update_fields=["area"])
        self.client.force_login(self.membro)
        self.assertNotContains(self.client.get(reverse("gerenciamento:mencoes")), "Decisão")
        self.assertEqual(self.client.post(reverse("gerenciamento:ler_mencoes", args=[self.pauta.pk])).status_code, 404)
