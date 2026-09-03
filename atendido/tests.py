from django.test import TestCase

# Create your tests here.
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from .models import ListaEspera


class ListaEsperaTest(TestCase):
    def test_calcula_sala_por_faixa_etaria(self):
        casos = {
            3: "VIOLETA", 4: "VIOLETA", 5: "ANIL", 6: "ANIL",
            7: "AZUL", 9: "VERDE", 11: "AMARELO", 13: "LARANJA",
            15: "VERMELHO", 17: "VERMELHO",
            18: "FAMILIA_FELIZ", 40: "FAMILIA_FELIZ",
        }
        for idade, sala in casos.items():
            with self.subTest(idade=idade):
                self.assertEqual(ListaEspera.calcular_sala(idade), sala)

    def test_calcula_idade_considerando_aniversario(self):
        hoje = date(2026, 7, 28)
        self.assertEqual(ListaEspera.calcular_idade(date(2021, 7, 28), hoje), 5)
        self.assertEqual(ListaEspera.calcular_idade(date(2021, 7, 29), hoje), 4)

    def test_rejeita_idade_fora_da_lista(self):
        registro = ListaEspera(
            nome_atendido="Criança",
            data_nascimento=date(2024, 1, 1),
            nome_responsavel="Responsável",
            contato_responsavel="12999999999",
        )
        with self.assertRaises(ValidationError):
            registro.full_clean()

    def _registro(self, *, parente, renda, pessoas, preenchimento):
        return ListaEspera(
            nome_atendido="Criança",
            data_nascimento=date(2018, 1, 1),
            nome_responsavel="Responsável",
            contato_responsavel="12999999999",
            parente_dentro_projeto=parente,
            renda_familiar=renda,
            quantidade_pessoas_familia=pessoas,
            data_preenchimento=timezone.make_aware(preenchimento),
        )

    def test_prioriza_parente_antes_da_renda(self):
        sem_parente = self._registro(
            parente=False, renda="MENOS DE 1000", pessoas=10,
            preenchimento=datetime(2025, 1, 1),
        )
        com_parente = self._registro(
            parente=True, renda="MAIS DE 5000", pessoas=1,
            preenchimento=datetime(2026, 1, 1),
        )
        self.assertEqual(
            sorted([sem_parente, com_parente], key=lambda item: item.chave_prioridade())[0],
            com_parente,
        )

    def test_prioriza_renda_per_capita_e_depois_data(self):
        mais_antigo = self._registro(
            parente=False, renda="ENTRE 1000-1500", pessoas=2,
            preenchimento=datetime(2025, 1, 1),
        )
        menor_per_capita = self._registro(
            parente=False, renda="MENOS DE 1000", pessoas=4,
            preenchimento=datetime(2026, 1, 1),
        )
        mesma_renda_mais_novo = self._registro(
            parente=False, renda="ENTRE 1000-1500", pessoas=2,
            preenchimento=datetime(2025, 2, 1),
        )
        ordenados = sorted(
            [mais_antigo, mesma_renda_mais_novo, menor_per_capita],
            key=lambda item: item.chave_prioridade(),
        )
        self.assertEqual(ordenados, [menor_per_capita, mais_antigo, mesma_renda_mais_novo])


class AtendidoDesativadoSomeDasListagensTest(TestCase):
    """Desativar é arquivar: some das telas, continua inteiro no admin.

    O campo `ativo` existia desde o começo, com o help_text mandando desmarcar
    em vez de excluir — mas nenhuma tela olhava para ele. Quem desmarcava
    continuava vendo a criança em tudo.
    """

    def setUp(self):
        from .models import Atendido
        self.ativa = Atendido.objects.create(
            nome="Ana Ativa", data_nascimento=date(2016, 5, 2), sala="AZUL",
        )
        self.desativada = Atendido.objects.create(
            nome="Bia Desativada", data_nascimento=date(2016, 6, 3), sala="AZUL",
            ativo=False,
        )

    def test_ativos_exclui_quem_foi_desativado(self):
        from .models import Atendido
        self.assertQuerySetEqual(
            Atendido.objects.ativos(), [self.ativa], transform=lambda x: x,
        )

    def test_admin_continua_enxergando_os_dois(self):
        """O gerenciador padrão não filtra nada — é por ele que o admin lista."""
        from .models import Atendido
        self.assertEqual(Atendido.objects.count(), 2)
        self.assertIn(self.desativada, Atendido.objects.all())

    def test_contagem_das_salas_na_navbar_ignora_desativados(self):
        """Esse contexto entra em TODOS os templates: errar aqui erra em tudo."""
        from .novos_context import atendidos_filtrados
        azul = atendidos_filtrados(request=None)["atendidos_azul"]
        self.assertQuerySetEqual(azul, [self.ativa], transform=lambda x: x)

    def test_a_listagem_de_atendidos_nao_traz_desativados(self):
        """Chamando o get_queryset direto: o test client quebra no Python 3.14
        ao renderizar template, e o que importa aqui é a consulta."""
        from .views import ListaAtendido
        self.assertQuerySetEqual(
            ListaAtendido().get_queryset(), [self.ativa], transform=lambda x: x,
        )
