"""Consultas de leitura do Financeiro que outras áreas reaproveitam.

Vive fora de views.py porque a revista do CR/RE precisa dos mesmos números:
importar uma view a partir de outro app amarraria os dois lados por acidente.
"""

from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum

from voluntario.models import LISTA_AREAS

from .models import Conta, Lancamento, RecargaCartao, TetoArea

# Lançamento sem categoria não deveria existir, mas a tela vai para o doador:
# uma linha em branco na prestação de contas é pior que um rótulo honesto.
SEM_CATEGORIA = 'Sem categoria'

# Mesma ideia para a área: despesa antiga não tem área gravada, e some-la num
# rótulo honesto é melhor que apagar o valor da tela.
SEM_AREA = 'Sem área definida'

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


def _percentual(valor, base):
    """Percentual com uma casa, sem estourar quando a base é zero.

    Base zero acontece de verdade: mês sem despesa nenhuma e teto zerado. Uma
    ZeroDivisionError aqui derrubaria a tela que o voluntário abre.
    """
    if not base:
        return Decimal('0.0')
    return (Decimal(valor) / Decimal(base) * CEM).quantize(UMA_CASA)


def limites_do_semestre(referencia):
    """Primeiro e último dia do semestre da data dada, com as duas pontas dentro.

    Janeiro–junho ou julho–dezembro. O teto é por semestre, então é este
    intervalo que decide o que já foi usado.
    """
    if referencia.month <= 6:
        return date(referencia.year, 1, 1), date(referencia.year, 6, 30)
    return date(referencia.year, 7, 1), date(referencia.year, 12, 31)


def rotulo_do_semestre(referencia):
    """'1º semestre de 2026' — o que a tela mostra."""
    numero = 1 if referencia.month <= 6 else 2
    return f'{numero}º semestre de {referencia.year}'


def _despesa_agrupada_por_area(inicio, fim):
    """Uma consulta só: área -> (valor somado, quantidade de lançamentos)."""
    return list(
        Lancamento.objects
        .filter(tipo='DESPESA', data__range=(inicio, fim))
        .values('area')
        .annotate(valor_total=Sum('valor'), quantidade=Count('id'))
        .order_by('-valor_total')
    )


def gasto_por_area(inicio, fim):
    """Quanto cada área gastou no período, da maior para a menor.

    Devolve (linhas, total). Uma linha por área COM gasto — área sem despesa
    no período não vira linha vazia, porque a tela é sobre para onde o dinheiro
    foi. O período inclui as duas pontas.
    """
    rotulos = dict(LISTA_AREAS)
    agregado = _despesa_agrupada_por_area(inicio, fim)

    # O total sai da soma das linhas já trazidas: um segundo aggregate() só
    # repetiria a mesma varredura para chegar ao mesmo número.
    total = sum(
        (linha['valor_total'] or Decimal('0') for linha in agregado),
        Decimal('0'),
    )

    linhas = []
    for linha in agregado:
        area = linha['area'] or ''
        valor = linha['valor_total'] or Decimal('0')
        linhas.append({
            'area': area,
            'nome': rotulos.get(area, SEM_AREA),
            'valor': valor,
            'percentual': _percentual(valor, total),
            'lancamentos': linha['quantidade'],
        })
    return linhas, total


def _ordem_do_teto(linha):
    """Quem precisa de atenção sobe: teto estourado, depois gasto sem teto (o
    furo que a tela existe para denunciar), depois o teto mais apertado."""
    if linha['estourou']:
        grupo = 0
    elif linha['sem_teto']:
        grupo = 1
    else:
        grupo = 2
    return (grupo, -linha['percentual'], -linha['gasto'], linha['nome'])


def _linha_do_teto(area, rotulos, teto, gasto):
    """Monta a linha de uma área no mês. Separada da consulta para que os casos
    de borda (teto zero, teto ausente) possam ser exercitados sem banco."""
    sem_teto = teto is None

    if sem_teto:
        # Sem teto não há de que tirar percentual nem quanto ainda sobra: o que
        # a tela precisa dizer é "gastou sem teto definido", não um número
        # inventado.
        percentual = Decimal('0.0')
        disponivel = Decimal('0')
        estourou = False
    elif teto == 0:
        # Teto zero com gasto é estouro total. 100% é o que a barra deve
        # mostrar; dividir por zero para descobrir isso derrubaria a tela.
        percentual = Decimal('100.0') if gasto > 0 else Decimal('0.0')
        disponivel = -gasto
        estourou = gasto > 0
    else:
        percentual = _percentual(gasto, teto)
        disponivel = teto - gasto
        estourou = gasto > teto

    return {
        'area': area,
        'nome': rotulos.get(area, SEM_AREA),
        'teto': teto,
        'gasto': gasto,
        'disponivel': disponivel,
        'percentual': percentual,
        'estourou': estourou,
        'sem_teto': sem_teto,
    }


def situacao_dos_tetos(referencia):
    """Teto x gasto de cada área no semestre — a tela que o voluntário abre.

    O teto é UM por área e vale até alguém alterar ou excluir; o que muda de
    período é o gasto, medido no semestre da data dada.

    Entram as áreas COM teto definido E as que gastaram sem ter teto: gasto sem
    teto é justamente o que a tela precisa denunciar, e esconder deixaria o
    furo invisível.

    Devolve lista de dicts com area, nome, teto (Decimal ou None), gasto,
    disponivel, percentual, estourou e sem_teto.
    """
    inicio, fim = limites_do_semestre(referencia)
    rotulos = dict(LISTA_AREAS)

    tetos = {teto.area: teto.valor for teto in TetoArea.objects.all()}
    gastos = {
        linha['area']: (linha['valor_total'] or Decimal('0'))
        for linha in _despesa_agrupada_por_area(inicio, fim)
        # Despesa sem área não pertence a teto de ninguém: entrar aqui como
        # "gastou sem teto" acusaria uma área que não existe.
        if linha['area']
    }

    linhas = [
        _linha_do_teto(area, rotulos, tetos.get(area), gastos.get(area, Decimal('0')))
        for area in set(tetos) | set(gastos)
    ]
    linhas.sort(key=_ordem_do_teto)
    return linhas


def saldo_das_contas():
    """Saldo de cada conta que controla saldo: recarga menos gasto.

    Três consultas fixas e nenhuma dentro do laço — as propriedades do model
    fazem uma consulta por conta, o que é aceitável numa tela de detalhe e
    caro numa lista.
    """
    contas = list(Conta.objects.filter(controla_saldo=True).select_related('responsavel'))
    if not contas:
        return []

    identificadores = [conta.pk for conta in contas]
    recargas = {
        linha['conta_id']: (linha['total'] or Decimal('0'))
        for linha in (RecargaCartao.objects
                      .filter(conta_id__in=identificadores)
                      .values('conta_id')
                      .annotate(total=Sum('valor')))
    }
    gastos = {
        linha['conta_id']: (linha['total'] or Decimal('0'))
        for linha in (Lancamento.objects
                      .filter(tipo='DESPESA', conta_id__in=identificadores)
                      .values('conta_id')
                      .annotate(total=Sum('valor')))
    }

    linhas = []
    for conta in contas:
        recarregado = recargas.get(conta.pk, Decimal('0'))
        gasto = gastos.get(conta.pk, Decimal('0'))
        saldo = recarregado - gasto
        linhas.append({
            'conta': conta,
            'recarregado': recarregado,
            'gasto': gasto,
            'saldo': saldo,
            'negativo': saldo < 0,
        })
    return linhas
