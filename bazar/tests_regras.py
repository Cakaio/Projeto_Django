"""Testes das regras do Bazar.

O Bazar acontece uma vez por ano, num sábado de manhã, com fila. Não existe
"corrigimos na próxima versão": o que estiver errado vira criança sem roupa ou
conta que não fecha no fim do dia. Por isso as regras são testadas sozinhas,
sem HTTP.
"""
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from atendido.models import Atendido
from voluntario.models import Voluntario

from .models import Bazar, Categoria, ItemRetirada, Retirada
from .regras import (RetiradaInvalida, conferir_pedido, estoque_estourado,
                     finalizar_retirada, ja_retirou_nesta_etapa,
                     numeros_do_bazar, por_salinha, saldo_de,
                     situacao_do_atendido)


class BaseBazar(TestCase):
    def setUp(self):
        self.bazar = Bazar.objects.create(
            nome="Bazar 2026", cota_inicial=5, etapa=Bazar.Etapa.PRIMEIRA)

        self.camiseta = Categoria.objects.create(
            bazar=self.bazar, nome="Camiseta", pontos=1,
            estoque_inicial=100, ordem=1)
        self.calca = Categoria.objects.create(
            bazar=self.bazar, nome="Calça", pontos=2,
            estoque_inicial=50, ordem=2)
        self.calcado = Categoria.objects.create(
            bazar=self.bazar, nome="Calçado", pontos=3,
            estoque_inicial=4, ordem=3)

        self.voluntario = Voluntario.objects.create_user(
            username="maria", password="senha-de-teste-123", area="EVENTOS")
        self.joao = self.criar_atendido("João", "VIOLETA")

    def criar_atendido(self, nome, sala="VIOLETA"):
        return Atendido.objects.create(
            nome=nome, sala=sala,
            data_nascimento=date(2015, 3, 10))

    def retirar(self, pedido, atendido=None, **extras):
        return finalizar_retirada(
            bazar=self.bazar,
            atendido=atendido or self.joao,
            pedido=pedido,
            conferido_por=self.voluntario,
            **extras,
        )


class SaldoTest(BaseBazar):

    def test_comeca_com_a_cota_cheia(self):
        self.assertEqual(saldo_de(self.bazar, self.joao), 5)

    def test_retirada_desconta(self):
        self.retirar({self.camiseta.pk: 2, self.calca.pk: 1})   # 2 + 2 = 4
        self.assertEqual(saldo_de(self.bazar, self.joao), 1)

    def test_o_saldo_e_por_pessoa(self):
        self.retirar({self.camiseta.pk: 4})
        maria = self.criar_atendido("Maria", "AZUL")
        self.assertEqual(saldo_de(self.bazar, maria), 5)

    def test_na_segunda_etapa_nao_existe_saldo(self):
        """A liderança decidiu que a 2ª etapa é livre — mostrar zero enganaria."""
        self.bazar.etapa = Bazar.Etapa.SEGUNDA
        self.bazar.save()
        self.assertIsNone(saldo_de(self.bazar, self.joao))

    def test_rascunho_nao_consome_saldo(self):
        """Retirada não finalizada é como se não existisse."""
        Retirada.objects.create(
            bazar=self.bazar, atendido=self.joao,
            etapa=Retirada.Etapa.PRIMEIRA, conferido_por=self.voluntario)
        self.assertEqual(saldo_de(self.bazar, self.joao), 5)


class ValidacaoTest(BaseBazar):

    def test_nao_deixa_passar_do_saldo(self):
        """Sacola que soma mais que a cota é recusada inteira.

        Na 1ª etapa cada pessoa passa UMA vez, então a conta é sempre a sacola
        inteira contra a cota inteira — não existe "vou completando".
        """
        with self.assertRaises(RetiradaInvalida) as erro:
            self.retirar({self.camiseta.pk: 3, self.calcado.pk: 1})   # 3+3 = 6 > 5
        self.assertIn("Pontos insuficientes", str(erro.exception))

    def test_saldo_parcial_na_segunda_passagem_da_segunda_etapa(self):
        """O exemplo do PRD (saldo 2, calçado de 3) só existe se sobrar saldo.

        Como a 1ª etapa é passagem única, o caso aparece quando a coordenação
        corrige uma retirada. O cálculo do saldo tem que continuar certo.
        """
        self.retirar({self.camiseta.pk: 3})       # usou 3, sobram 2
        self.assertEqual(saldo_de(self.bazar, self.joao), 2)

    def test_a_mensagem_diz_o_saldo_e_o_total(self):
        """O voluntário está com uma criança na frente: precisa do número."""
        with self.assertRaises(RetiradaInvalida) as erro:
            self.retirar({self.calcado.pk: 2})    # 6 > 5
        texto = str(erro.exception)
        self.assertIn("5", texto)
        self.assertIn("6", texto)

    def test_gastar_exatamente_a_cota_pode(self):
        self.retirar({self.camiseta.pk: 5})
        self.assertEqual(saldo_de(self.bazar, self.joao), 0)

    def test_na_segunda_etapa_nao_valida_pontos(self):
        """Ali o objetivo é esvaziar o estoque, não racionar."""
        self.bazar.etapa = Bazar.Etapa.SEGUNDA
        self.bazar.save()
        retirada, total, _ = self.retirar({self.calcado.pk: 10})
        self.assertEqual(total, 30)
        self.assertTrue(retirada.esta_finalizada)

    def test_sacola_vazia_e_recusada(self):
        with self.assertRaises(RetiradaInvalida) as erro:
            self.retirar({self.camiseta.pk: 0})
        self.assertIn("Nenhuma peça", str(erro.exception))

    def test_bazar_fechado_nao_aceita_retirada(self):
        self.bazar.etapa = Bazar.Etapa.NAO_COMECOU
        self.bazar.save()
        with self.assertRaises(RetiradaInvalida) as erro:
            self.retirar({self.camiseta.pk: 1})
        self.assertIn("não está aberto", str(erro.exception))


class RetiradaDuplicadaTest(BaseBazar):
    """A trava contra passar duas vezes pela mesma fila."""

    def test_segunda_passagem_na_mesma_etapa_e_recusada(self):
        self.retirar({self.camiseta.pk: 1})
        with self.assertRaises(RetiradaInvalida) as erro:
            self.retirar({self.camiseta.pk: 1})
        self.assertIn("já finalizou", str(erro.exception))

    def test_mesmo_com_saldo_sobrando_nao_passa_de_novo(self):
        """Sobrar ponto não dá direito a uma segunda passagem na 1ª etapa."""
        self.retirar({self.camiseta.pk: 1})       # usou 1 de 5
        self.assertTrue(ja_retirou_nesta_etapa(self.bazar, self.joao))
        with self.assertRaises(RetiradaInvalida):
            self.retirar({self.camiseta.pk: 1})

    def test_a_segunda_etapa_libera_de_novo(self):
        """Etapa nova é fila nova — sem apagar o histórico da primeira."""
        self.retirar({self.camiseta.pk: 5})
        self.bazar.etapa = Bazar.Etapa.SEGUNDA
        self.bazar.save()

        retirada, _, _ = self.retirar({self.calca.pk: 1})
        self.assertEqual(retirada.etapa, Retirada.Etapa.SEGUNDA)
        self.assertEqual(
            Retirada.objects.filter(atendido=self.joao).count(), 2)


class EstoqueTest(BaseBazar):

    def test_distribuido_e_restante_acompanham_a_retirada(self):
        self.retirar({self.camiseta.pk: 3})
        self.camiseta.refresh_from_db()
        self.assertEqual(self.camiseta.distribuido, 3)
        self.assertEqual(self.camiseta.restante, 97)

    def test_rascunho_nao_baixa_estoque(self):
        Retirada.objects.create(
            bazar=self.bazar, atendido=self.joao,
            etapa=Retirada.Etapa.PRIMEIRA, conferido_por=self.voluntario)
        self.assertEqual(self.camiseta.distribuido, 0)

    def test_estoque_estourado_avisa_mas_nao_bloqueia(self):
        """Contagem de bazar é aproximada.

        Travar a entrega porque a planilha diz que acabou seria deixar a criança
        sem a peça que já está na mão do voluntário. Quem decide é a pessoa.
        """
        retirada, _, alertas = self.retirar({self.calcado.pk: 1})  # estoque 4
        self.assertTrue(retirada.esta_finalizada)
        self.assertEqual(alertas, [])

        maria = self.criar_atendido("Maria")
        self.calcado.estoque_inicial = 1
        self.calcado.save()
        retirada2, _, alertas2 = self.retirar({self.calcado.pk: 1}, atendido=maria)

        self.assertTrue(retirada2.esta_finalizada)   # entregou assim mesmo
        self.assertEqual(len(alertas2), 1)
        self.assertIn("Calçado", alertas2[0])

    def test_categoria_sem_estoque_cadastrado_nao_alerta(self):
        """Zero em estoque_inicial significa "não controlo", não "acabou"."""
        brinquedo = Categoria.objects.create(
            bazar=self.bazar, nome="Brinquedo", pontos=1, estoque_inicial=0)
        self.assertIsNone(brinquedo.restante)

        # Na 2ª etapa não há cota, então dá para pedir muito e testar só o
        # estoque, sem esbarrar na validação de pontos.
        self.bazar.etapa = Bazar.Etapa.SEGUNDA
        self.bazar.save()
        _, _, alertas = self.retirar({brinquedo.pk: 99})
        self.assertEqual(alertas, [])


class HistoricoTest(BaseBazar):

    def test_o_valor_da_peca_fica_congelado_na_retirada(self):
        """Se a coordenação corrigir o preço no meio, o passado não muda.

        Sem isso o relatório do fim do dia contaria uma história diferente da
        que aconteceu na fila.
        """
        self.retirar({self.calca.pk: 1})           # 2 pontos
        self.calca.pontos = 3
        self.calca.save()

        item = ItemRetirada.objects.get(categoria=self.calca)
        self.assertEqual(item.pontos_unitarios, 2)
        self.assertEqual(item.pontos_total, 2)

    def test_situacao_traz_historico_das_duas_etapas(self):
        self.retirar({self.camiseta.pk: 2, self.calca.pk: 1})   # 4 pontos
        self.bazar.etapa = Bazar.Etapa.SEGUNDA
        self.bazar.save()
        self.retirar({self.calcado.pk: 1})                      # 3 pontos

        situacao = situacao_do_atendido(self.bazar, self.joao)
        self.assertEqual(len(situacao["historico"]), 2)
        self.assertEqual(
            sum(r.pontos_usados for r in situacao["historico"]), 7)

    def test_situacao_traz_a_numeracao_da_ficha(self):
        """Dado que o projeto já tem e que economiza tempo na fila."""
        self.joao.numeracao_camisa = "10"
        self.joao.numeracao_calcado = "32"
        self.joao.save()

        situacao = situacao_do_atendido(self.bazar, self.joao)
        self.assertEqual(situacao["numeracoes"]["camisa"], "10")
        self.assertEqual(situacao["numeracoes"]["calcado"], "32")

    def test_registra_quem_levou_a_sacola(self):
        """O atendido nem sempre está presente."""
        retirada, _, _ = self.retirar(
            {self.camiseta.pk: 1},
            retirado_por=Retirada.RetiradoPor.PAI_MAE,
            retirado_por_nome="Ana, mãe do João",
            sala_do_bazar="Sala 1")

        self.assertEqual(retirada.retirado_por, Retirada.RetiradoPor.PAI_MAE)
        self.assertEqual(retirada.retirado_por_nome, "Ana, mãe do João")
        self.assertEqual(retirada.sala_do_bazar, "Sala 1")
        self.assertEqual(retirada.conferido_por, self.voluntario)


class NumerosTest(BaseBazar):

    def test_conta_atendidos_pecas_e_pontos(self):
        self.retirar({self.camiseta.pk: 2, self.calca.pk: 1})   # 3 peças, 4 pts
        maria = self.criar_atendido("Maria", "AZUL")
        self.retirar({self.camiseta.pk: 1}, atendido=maria)     # 1 peça, 1 pt

        numeros = numeros_do_bazar(self.bazar)
        self.assertEqual(numeros["atendidos"], 2)
        self.assertEqual(numeros["pecas"], 4)
        self.assertEqual(numeros["pontos"], 5)
        self.assertEqual(numeros["primeira"], 2)
        self.assertEqual(numeros["segunda"], 0)

    def test_quem_passou_nas_duas_etapas_conta_uma_vez_no_total(self):
        """Senão o painel diria que atendeu mais gente do que atendeu."""
        self.retirar({self.camiseta.pk: 1})
        self.bazar.etapa = Bazar.Etapa.SEGUNDA
        self.bazar.save()
        self.retirar({self.camiseta.pk: 1})

        numeros = numeros_do_bazar(self.bazar)
        self.assertEqual(numeros["atendidos"], 1)
        self.assertEqual(numeros["primeira"], 1)
        self.assertEqual(numeros["segunda"], 1)

    def test_por_salinha_mostra_ate_as_zeradas(self):
        """A sala que ainda não veio é a informação que a coordenação usa."""
        self.retirar({self.camiseta.pk: 1})   # João é da Violeta
        linhas = {linha["sala"]: linha["total"] for linha in por_salinha(self.bazar)}

        self.assertEqual(linhas["Violeta"], 1)
        self.assertEqual(linhas["Azul"], 0)
        self.assertIn("Família Feliz", linhas)


class UmBazarAbertoTest(TestCase):
    """Dois abertos ao mesmo tempo significaria duas telas gravando em edições
    diferentes no mesmo dia, e ninguém perceberia até fechar a conta."""

    def test_nao_deixa_abrir_dois(self):
        Bazar.objects.create(nome="Bazar 2026", etapa=Bazar.Etapa.PRIMEIRA)
        segundo = Bazar(nome="Outro", etapa=Bazar.Etapa.PRIMEIRA)

        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            segundo.full_clean()

    def test_encerrado_nao_atrapalha_o_proximo(self):
        Bazar.objects.create(nome="Bazar 2025", etapa=Bazar.Etapa.ENCERRADO)
        novo = Bazar(nome="Bazar 2026", etapa=Bazar.Etapa.PRIMEIRA,
                     data=timezone.localdate())
        novo.full_clean()   # não levanta

    def test_em_andamento_acha_o_aberto(self):
        Bazar.objects.create(nome="Velho", etapa=Bazar.Etapa.ENCERRADO)
        aberto = Bazar.objects.create(nome="Hoje", etapa=Bazar.Etapa.SEGUNDA)
        self.assertEqual(Bazar.em_andamento(), aberto)
