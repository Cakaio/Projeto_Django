from decimal import Decimal

from django.test import SimpleTestCase

from .models import Material
from .forms import MaterialForm


class MaterialValorTotalTests(SimpleTestCase):
    def test_valor_total_multiplica_valor_unitario_pela_quantidade(self):
        material = Material(quantidade=Decimal("2.50"), valor=Decimal("8.20"))

        self.assertEqual(material.valor_total, Decimal("20.5000"))

    def test_valor_total_sem_valor_retorna_none(self):
        material = Material(quantidade=Decimal("4.00"), valor=None)

        self.assertIsNone(material.valor_total)


class MaterialLinkTests(SimpleTestCase):
    def test_formulario_rejeita_link_invalido(self):
        form = MaterialForm(data={
            "nome": "Cartolina",
            "link": "link-invalido",
            "quantidade": "1",
            "valor": "",
            "local": "",
            "pedido": "SUPPLY",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("link", form.errors)

    def test_formulario_disponibiliza_campo_especificar(self):
        self.assertIn("especificar", MaterialForm().fields)

    def test_material_possui_relacao_com_requisitante(self):
        field = Material._meta.get_field("requisitado_por")

        self.assertEqual(field.remote_field.model._meta.label, "voluntario.Voluntario")
