from decimal import Decimal

from django.test import SimpleTestCase

from .models import Local, Pedido
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
            "unidade": "UN",
            "sabado": "",
            "area": "",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("link", form.errors)
