from datetime import date
from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from sabado.models import Sabado
from semanario.models import Atividade, Material, Semanario
from voluntario.models import Voluntario

from .models import Item, Local, Pedido
from .forms import ItemForm, LocalForm, PedidoForm


class LocalTests(SimpleTestCase):
    def test_descricao_exibe_nome_e_tipo(self):
        local = Local(nome="Papelaria Central", tipo="PAPELARIA")

        self.assertEqual(str(local), "Papelaria Central — Papelaria")


class PedidoValorTotalTests(SimpleTestCase):
    def test_valor_total_multiplica_valor_unitario_pela_quantidade(self):
        pedido = Pedido(quantidade=Decimal("3.50"), valor=Decimal("12.40"))

        self.assertEqual(pedido.valor_total, Decimal("43.4000"))

    def test_valor_total_sem_valor_retorna_none(self):
        pedido = Pedido(quantidade=Decimal("2.00"), valor=None)

        self.assertIsNone(pedido.valor_total)


class PedidoLinkTests(SimpleTestCase):
    def test_formulario_rejeita_link_invalido(self):
        form = PedidoForm(data={
            "nome": "Cola",
            "link": "link-invalido",
            "quantidade": "1",
            "sabado": "",
            "area": "",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("link", form.errors)

    def test_formulario_disponibiliza_campo_especificar(self):
        self.assertIn("especificar", PedidoForm().fields)


class CadastroFormsTests(SimpleTestCase):
    def test_item_form_aplica_classes_do_design_system(self):
        form = ItemForm()

        self.assertEqual(form.fields["nome"].widget.attrs["class"], "pcf-input")
        self.assertEqual(form.fields["categoria"].widget.attrs["class"], "pcf-input")

    def test_local_form_aplica_classes_do_design_system(self):
        form = LocalForm()

        self.assertEqual(form.fields["nome"].widget.attrs["class"], "pcf-input")
        self.assertEqual(form.fields["site"].widget.attrs["class"], "pcf-input")


class CadastroSupplyViewTests(TestCase):
    def setUp(self):
        self.usuario = Voluntario.objects.create_user(
            username="cadastro-supply",
            password="teste",
            area="SUPPLY",
        )
        self.client.force_login(self.usuario)

    def test_painel_exibe_cards_de_cadastro(self):
        resposta = self.client.get(reverse("supply:supply_view"))

        self.assertContains(resposta, reverse("supply:cadastrar_item"))
        self.assertContains(resposta, "Cadastro de Item")
        self.assertContains(resposta, reverse("supply:cadastrar_local"))
        self.assertContains(resposta, "Cadastro de Locais")

    def test_paginas_de_cadastro_renderizam_os_formularios(self):
        casos = (
            ("supply:cadastrar_item", "supply/cadastro_item.html", "Salvar item"),
            ("supply:cadastrar_local", "supply/cadastro_local.html", "Salvar local"),
        )

        for rota, template, texto_botao in casos:
            with self.subTest(rota=rota):
                resposta = self.client.get(reverse(rota))
                self.assertEqual(resposta.status_code, 200)
                self.assertTemplateUsed(resposta, template)
                self.assertContains(resposta, texto_botao)

    def test_cadastra_item_e_exibe_mensagem_de_sucesso(self):
        resposta = self.client.post(reverse("supply:cadastrar_item"), {
            "nome": "Cartolina colorida",
            "descricao": "Pacote com cores variadas",
            "categoria": "PAPELARIA",
            "unidade": "PAC",
            "quantidade_minima": "5.00",
            "ativo": "on",
        })

        self.assertRedirects(
            resposta,
            reverse("supply:supply_view"),
            fetch_redirect_response=False,
        )
        self.assertTrue(Item.objects.filter(nome="Cartolina colorida").exists())
        mensagens = [str(message) for message in get_messages(resposta.wsgi_request)]
        self.assertIn('Item "Cartolina colorida" cadastrado com sucesso.', mensagens)

    def test_cadastra_local_e_exibe_mensagem_de_sucesso(self):
        resposta = self.client.post(reverse("supply:cadastrar_local"), {
            "nome": "Papelaria Central",
            "tipo": "PAPELARIA",
            "localizacao": "Rua das Flores, 100",
            "cidade": "São Paulo",
            "numero_contato": "(11) 99999-0000",
            "whatsapp": "on",
            "email": "contato@papelaria.example",
            "site": "https://papelaria.example",
            "observacoes": "Entrega aos sábados",
            "ativo": "on",
        })

        self.assertRedirects(
            resposta,
            reverse("supply:supply_view"),
            fetch_redirect_response=False,
        )
        self.assertTrue(Local.objects.filter(nome="Papelaria Central").exists())
        mensagens = [str(message) for message in get_messages(resposta.wsgi_request)]
        self.assertIn('Local "Papelaria Central" cadastrado com sucesso.', mensagens)


class GerenciarMaterialPainelTests(TestCase):
    def setUp(self):
        self.usuario = Voluntario.objects.create_user(
            username="supply", password="teste", area="SUPPLY"
        )
        self.sabado = Sabado.objects.create(
            data=date(2026, 12, 19), tema="Teste", descricao="Teste"
        )
        self.semanario = Semanario.objects.create(
            data=self.sabado, sala="AZUL", tema="Teste"
        )
        self.atividade = Atividade.objects.create(
            semanario=self.semanario, atividade="Atividade", descricao="Teste"
        )
        self.item = Item.objects.create(nome="Cartolina", unidade="UN")
        self.material = Material.objects.create(
            atividade=self.atividade,
            item=self.item,
            nome=self.item.nome,
            quantidade="2",
            pedido="SUPPLY",
            requisitado_por=self.usuario,
        )
        self.client.force_login(self.usuario)
        self.url = reverse("supply:gerenciar_item_painel")

    def dados(self, acao):
        return {
            "sabado": self.sabado.pk,
            # Sem filtro de local, o template antigo serializava None como
            # texto e o redirect voltava com ?local=None.
            "local": "None",
            "painel": "material",
            acao: self.material.pk,
        }

    def test_duplicar_material_retorna_ao_painel_sem_erro(self):
        resposta = self.client.post(
            self.url, self.dados("duplicar_material"), follow=True
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Material.objects.count(), 2)

    def test_excluir_material_retorna_ao_painel_sem_erro(self):
        resposta = self.client.post(
            self.url, self.dados("excluir_material"), follow=True
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Material.objects.filter(pk=self.material.pk).exists())


class FechamentoSabadoModelTests(TestCase):
    """Depois do sabado o Supply volta e corrige os gastos reais. Ate existir
    este registro a ADM nao tinha como saber se os numeros da tela ja eram os
    reais ou ainda os do planejamento — e perguntava no grupo toda semana."""

    def setUp(self):
        from supply.models import FechamentoSabado
        self.FechamentoSabado = FechamentoSabado
        self.sabado = Sabado.objects.create(
            data=date(2026, 9, 12), tema="Tema", descricao="d")
        self.ana = Voluntario.objects.create_user(
            username="ana_sup", password="pw", area="SUPPLY", first_name="Ana")
        self.bruno = Voluntario.objects.create_user(
            username="bruno_sup", password="pw", area="SUPPLY", first_name="Bruno")

    def test_nasce_com_as_duas_etapas_em_aberto(self):
        fechamento = self.FechamentoSabado.objects.create(sabado=self.sabado)
        self.assertFalse(fechamento.materiais_conferidos)
        self.assertFalse(fechamento.pedidos_conferidos)
        self.assertFalse(fechamento.completo)

    def test_marcar_grava_quem_e_quando(self):
        fechamento = self.FechamentoSabado.objects.create(sabado=self.sabado)
        fechamento.marcar("materiais", self.ana)
        fechamento.refresh_from_db()

        self.assertTrue(fechamento.materiais_conferidos)
        self.assertEqual(fechamento.materiais_conferidos_por, self.ana)
        self.assertIsNotNone(fechamento.materiais_conferidos_em)
        # A outra etapa nao e arrastada junto.
        self.assertFalse(fechamento.pedidos_conferidos)
        self.assertFalse(fechamento.completo)

    def test_as_duas_etapas_fecham_o_sabado(self):
        fechamento = self.FechamentoSabado.objects.create(sabado=self.sabado)
        fechamento.marcar("materiais", self.ana)
        fechamento.marcar("pedidos", self.bruno)
        self.assertTrue(fechamento.completo)

    def test_remarcar_troca_o_nome_e_a_hora(self):
        fechamento = self.FechamentoSabado.objects.create(sabado=self.sabado)
        fechamento.marcar("materiais", self.ana)
        primeira = fechamento.materiais_conferidos_em
        fechamento.marcar("materiais", self.bruno)
        fechamento.refresh_from_db()

        self.assertEqual(fechamento.materiais_conferidos_por, self.bruno)
        self.assertGreaterEqual(fechamento.materiais_conferidos_em, primeira)

    def test_desmarcar_limpa_os_dois_campos(self):
        """Nome sem data (ou data sem nome) seria meia verdade: a tela diria
        'conferido' sem saber quando, ou o contrario."""
        fechamento = self.FechamentoSabado.objects.create(sabado=self.sabado)
        fechamento.marcar("pedidos", self.ana)
        fechamento.desmarcar("pedidos")
        fechamento.refresh_from_db()

        self.assertIsNone(fechamento.pedidos_conferidos_por)
        self.assertIsNone(fechamento.pedidos_conferidos_em)
        self.assertFalse(fechamento.pedidos_conferidos)

    def test_etapa_desconhecida_e_recusada(self):
        fechamento = self.FechamentoSabado.objects.create(sabado=self.sabado)
        with self.assertRaises(ValueError):
            fechamento.marcar("lanches", self.ana)

    def test_um_fechamento_por_sabado(self):
        from django.db import IntegrityError
        self.FechamentoSabado.objects.create(sabado=self.sabado)
        with self.assertRaises(IntegrityError):
            self.FechamentoSabado.objects.create(sabado=self.sabado)

    def test_do_sabado_cria_uma_vez_so(self):
        """A tela nao pode precisar que alguem cadastre o fechamento antes."""
        primeiro = self.FechamentoSabado.do_sabado(self.sabado)
        segundo = self.FechamentoSabado.do_sabado(self.sabado)
        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(self.FechamentoSabado.objects.count(), 1)


class MarcarFechamentoViewTests(TestCase):
    """Quem marca sao SUPPLY e TRIADE — exatamente quem ja edita o painel de
    materiais. Ninguem ganha poder novo, e quem atualiza o gasto e quem
    confirma que atualizou."""

    def setUp(self):
        from supply.models import FechamentoSabado
        self.FechamentoSabado = FechamentoSabado
        self.sabado = Sabado.objects.create(
            data=date(2026, 9, 12), tema="Tema", descricao="d")
        self.ana = Voluntario.objects.create_user(
            username="ana_fech", password="pw", area="SUPPLY", first_name="Ana")
        self.triade = Voluntario.objects.create_user(
            username="tri_fech", password="pw", area="TRIADE")
        self.amarelo = Voluntario.objects.create_user(
            username="amr_fech", password="pw", area="AMARELO")

    def _postar(self, usuario, **dados):
        self.client.force_login(usuario)
        corpo = {"sabado": self.sabado.pk, "etapa": "materiais", "acao": "marcar"}
        corpo.update(dados)
        return self.client.post(reverse("supply:marcar_fechamento"), corpo)

    def test_supply_marca(self):
        resposta = self._postar(self.ana)
        self.assertEqual(resposta.status_code, 302)
        fechamento = self.FechamentoSabado.objects.get(sabado=self.sabado)
        self.assertTrue(fechamento.materiais_conferidos)
        self.assertEqual(fechamento.materiais_conferidos_por, self.ana)

    def test_triade_marca(self):
        self._postar(self.triade, etapa="pedidos")
        fechamento = self.FechamentoSabado.objects.get(sabado=self.sabado)
        self.assertTrue(fechamento.pedidos_conferidos)

    def test_area_de_fora_nao_marca(self):
        resposta = self._postar(self.amarelo)
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(self.FechamentoSabado.objects.exists())

    def test_deslogado_nao_marca(self):
        resposta = self.client.post(reverse("supply:marcar_fechamento"), {
            "sabado": self.sabado.pk, "etapa": "materiais", "acao": "marcar"})
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/login/", resposta.url)
        self.assertFalse(self.FechamentoSabado.objects.exists())

    def test_get_nao_marca(self):
        """Marcar muda estado: nao pode acontecer por alguem abrir uma URL."""
        self.client.force_login(self.ana)
        resposta = self.client.get(reverse("supply:marcar_fechamento"))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(self.FechamentoSabado.objects.exists())

    def test_desmarcar_volta_para_pendente(self):
        self._postar(self.ana)
        self._postar(self.ana, acao="desmarcar")
        fechamento = self.FechamentoSabado.objects.get(sabado=self.sabado)
        self.assertFalse(fechamento.materiais_conferidos)
        self.assertIsNone(fechamento.materiais_conferidos_por)

    def test_etapa_invalida_nao_derruba_a_tela(self):
        resposta = self._postar(self.ana, etapa="lanches")
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(
            self.FechamentoSabado.objects.filter(
                materiais_conferidos_em__isnull=False).exists())

    def test_volta_para_o_painel_do_mesmo_sabado(self):
        resposta = self._postar(self.ana, painel="pedido", local="2")
        self.assertIn(f"sabado={self.sabado.pk}", resposta.url)
        self.assertIn("painel=pedido", resposta.url)


class PainelMateriaisMostraFechamentoTests(TestCase):
    def setUp(self):
        from supply.models import FechamentoSabado
        self.FechamentoSabado = FechamentoSabado
        self.sabado = Sabado.objects.create(
            data=date(2026, 9, 12), tema="Tema", descricao="d")
        self.ana = Voluntario.objects.create_user(
            username="ana_painel", password="pw", area="SUPPLY", first_name="Ana")

    def _html(self):
        from django.test import RequestFactory
        from supply.views import painel_materiais
        requisicao = RequestFactory().get(
            f"/supply/painel_materiais/?sabado={self.sabado.pk}")
        requisicao.user = self.ana
        return painel_materiais(requisicao).content.decode()

    def test_faixa_oferece_marcar_as_duas_etapas(self):
        html = self._html()
        self.assertIn('name="etapa" value="materiais"', html)
        self.assertIn('name="etapa" value="pedidos"', html)

    def test_faixa_mostra_quem_conferiu(self):
        fechamento = self.FechamentoSabado.do_sabado(self.sabado)
        fechamento.marcar("materiais", self.ana)
        self.assertIn("Ana", self._html())
