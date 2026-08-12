"""Consultas de leitura do Financeiro que outras áreas reaproveitam.

Vive fora de views.py porque a revista do CR/RE precisa dos mesmos números:
importar uma view a partir de outro app amarraria os dois lados por acidente.
"""

from decimal import Decimal

from django.db.models import Count, Sum

from .models import Lancamento

# Lançamento sem categoria não deveria existir, mas a tela vai para o doador:
# uma linha em branco na prestação de contas é pior que um rótulo honesto.
SEM_CATEGORIA = 'Sem categoria'

CEM = Decimal('100')
UMA_CASA = Decimal('0.1')


def _linha_despesa(agrupamento, total):
    """Converte uma linha do agregado no formato que a tela e a revista usam.

    Separada da consulta para que o percentual — único ponto com risco de
    divisão por zero — possa ser exercitado sem depender do banco.
    """
    valor = agrupamento['valor_total'] or Decimal('0')

    if total:
        percentual = (valor / total * CEM).quantize(UMA_CASA)
    else:
        # Período sem nenhuma despesa: não há de que tirar percentual.
        percentual = Decimal('0.0')

    return {
        'nome': agrupamento['categoria__nome'] or SEM_CATEGORIA,
        'valor': valor,
        'percentual': percentual,
        'lancamentos': agrupamento['quantidade'],
    }


def despesas_por_categoria(inicio, fim):
    """Quanto saiu, por categoria, num período. É a tabela que o CR mostra ao
    doador ('seu dinheiro virou isto') e que também entra na revista.

    Devolve (linhas, total), onde cada linha tem nome, valor, percentual e
    lancamentos (quantidade). Ordenado do maior gasto para o menor.
    """
    agregado = list(
        Lancamento.objects
        .filter(tipo='DESPESA', data__range=(inicio, fim))
        .values('categoria__nome')
        .annotate(valor_total=Sum('valor'), quantidade=Count('id'))
        .order_by('-valor_total')
    )

    # O total sai da soma das linhas já trazidas: um segundo aggregate() no
    # banco só repetiria a mesma varredura para chegar ao mesmo número.
    total = sum(
        (linha['valor_total'] or Decimal('0') for linha in agregado),
        Decimal('0'),
    )

    return [_linha_despesa(linha, total) for linha in agregado], total
