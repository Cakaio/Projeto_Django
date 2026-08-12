from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from sabado.models import Sabado
from semanario.models import Atividade, Material, Semanario
from voluntario.models import Voluntario

from .models import Item, Local, Pedido
from .forms import PedidoForm


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
