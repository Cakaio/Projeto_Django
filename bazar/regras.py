"""As regras do Bazar, longe de HTTP.

Tudo que decide alguma coisa mora aqui: quanto a pessoa ainda tem, se pode
retirar, o que acontece ao finalizar. As views só perguntam.

A separação não é estética. O Bazar acontece uma vez por ano, num sábado de
manhã, com fila — não dá para descobrir no dia que a conta de pontos estava
errada. Regra isolada é regra que se testa direito.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import Bazar, Categoria, ItemRetirada, Retirada


# Quanto tempo quem acabou de gravar pode desfazer sozinho. Depois disso é a
# coordenação que corrige — pela tela do Bazar, não pelo admin do Django num
# celular, que o voluntário nem acessa.
MINUTOS_PARA_DESFAZER = 2


class RetiradaInvalida(Exception):
    """O que o voluntário tentou não pode ser feito, e a mensagem explica por quê."""


def pontos_usados_na_etapa(bazar, atendido, etapa):
    """Pontos já consumidos pelo atendido naquela etapa, só do que foi finalizado."""
    return ItemRetirada.objects.filter(
        retirada__bazar=bazar,
        retirada__atendido=atendido,
        retirada__etapa=etapa,
        retirada__finalizada_em__isnull=False,
    ).aggregate(total=Sum("pontos_total"))["total"] or 0


def saldo_de(bazar, atendido):
    """Quantos pontos o atendido ainda tem na 1ª etapa.

    Na 2ª etapa não existe saldo: a liderança decidiu que ali é livre, porque o
    objetivo passa a ser esvaziar o estoque. Devolve None para a tela saber que
    não há número a mostrar, em vez de mostrar um zero enganoso.
    """
    if bazar.etapa != Bazar.Etapa.PRIMEIRA:
        return None
    usados = pontos_usados_na_etapa(bazar, atendido, Retirada.Etapa.PRIMEIRA)
    return max(0, bazar.cota_inicial - usados)


def ja_retirou_nesta_etapa(bazar, atendido):
    """A trava contra passar duas vezes pela mesma fila.

    Só vale na 1ª ETAPA: na 2ª o objetivo declarado pela liderança é esvaziar o
    estoque, e ali a família que volta na arara está certa — a trava só
    produziria mensagem de erro para quem não errou, com a roupa na mão.

    Visitante (sem ficha) não trava: travar por nome barraria dois xarás.
    """
    if atendido is None or bazar.etapa != Bazar.Etapa.PRIMEIRA:
        return False
    return Retirada.objects.filter(
        bazar=bazar, atendido=atendido, etapa=bazar.etapa,
        finalizada_em__isnull=False,
    ).exists()


def situacao_do_atendido(bazar, atendido):
    """Tudo que a tela de atendimento precisa saber sobre a pessoa, de uma vez."""
    historico = list(
        Retirada.objects
        .filter(bazar=bazar, atendido=atendido, finalizada_em__isnull=False)
        .prefetch_related("itens__categoria")
        .order_by("criado_em")
    )
    return {
        "atendido": atendido,
        "saldo": saldo_de(bazar, atendido),
        "cota": bazar.cota_inicial,
        "usados_primeira": pontos_usados_na_etapa(
            bazar, atendido, Retirada.Etapa.PRIMEIRA),
        "ja_retirou": ja_retirou_nesta_etapa(bazar, atendido),
        "historico": historico,
        # Numeração que o projeto já guarda na ficha. Não estava no PRD, mas é a
        # informação que mais economiza tempo na fila de um bazar de roupa.
        "numeracoes": {
            "camisa": atendido.numeracao_camisa,
            "calca": atendido.numeracao_calca,
            "calcado": atendido.numeracao_calcado,
        },
    }


def conferir_pedido(bazar, atendido, pedido, sem_retirada=False):
    """Valida o carrinho antes de gravar. Devolve as linhas já calculadas.

    `pedido` é {categoria_id: quantidade}. Levanta RetiradaInvalida com um texto
    pronto para a tela — o voluntário está com uma criança na frente e precisa
    entender na hora, não depois.
    """
    if not bazar.esta_aberto:
        raise RetiradaInvalida("O Bazar não está aberto para retirada.")

    if ja_retirou_nesta_etapa(bazar, atendido):
        raise RetiradaInvalida(
            f"{atendido.nome} já finalizou a retirada desta etapa.")
    # (ja_retirou_nesta_etapa devolve False quando atendido é None, então a
    #  linha acima nunca desreferencia nulo.)

    linhas = []
    categorias = {
        categoria.pk: categoria
        for categoria in Categoria.objects.filter(bazar=bazar, ativo=True)
    }

    for categoria_id, quantidade in pedido.items():
        categoria = categorias.get(int(categoria_id))
        if categoria is None:
            raise RetiradaInvalida("Categoria não encontrada neste Bazar.")
        quantidade = int(quantidade)
        if quantidade <= 0:
            continue
        linhas.append({
            "categoria": categoria,
            "quantidade": quantidade,
            "pontos_unitarios": categoria.pontos,
            "pontos_total": categoria.pontos * quantidade,
        })

    if not linhas:
        # Vazio POR ENGANO e vazio DE PROPÓSITO são coisas diferentes. O segundo
        # é comparecimento sem retirada — a criança veio, foi conferida e não
        # achou nada do tamanho dela. É a evidência mais direta de que faltou
        # tamanho, e a coordenação precisa enxergá-la.
        if sem_retirada:
            return [], 0
        raise RetiradaInvalida("Nenhuma peça foi registrada.")

    if sem_retirada:
        raise RetiradaInvalida(
            'Ou marque "não levou nada", ou registre as peças — não os dois.')

    total = sum(linha["pontos_total"] for linha in linhas)

    if bazar.desconta_pontos:
        if atendido is not None:
            saldo = saldo_de(bazar, atendido)
            if total > saldo:
                raise RetiradaInvalida(
                    f"Pontos insuficientes. {atendido.nome} tem {saldo} "
                    f"ponto{'s' if saldo != 1 else ''} e a sacola soma {total}.")
        elif total > bazar.cota_inicial:
            # Visitante não tem histórico para consultar: a cota inteira é o
            # limite, porque é a primeira e única passagem dele.
            raise RetiradaInvalida(
                f"A cota é de {bazar.cota_inicial} pontos e a sacola soma "
                f"{total}.")

    return linhas, total


def estoque_estourado(linhas):
    """Categorias em que o pedido passa do que resta em estoque.

    AVISA, não bloqueia. Contagem de estoque num bazar é aproximada: travar a
    entrega de uma roupa porque a planilha diz que acabou seria deixar a criança
    sem a peça que está na mão do voluntário. Quem decide é a pessoa, não o
    número.
    """
    alertas = []
    for linha in linhas:
        categoria = linha["categoria"]
        restante = categoria.restante
        if restante is not None and linha["quantidade"] > restante:
            alertas.append(
                f"{categoria.nome}: restam {restante} no controle e "
                f"foram registradas {linha['quantidade']}.")
    return alertas


@transaction.atomic
def finalizar_retirada(*, bazar, atendido, pedido, conferido_por,
                       sala=None, sala_do_bazar="",
                       retirado_por=Retirada.RetiradoPor.ATENDIDO,
                       retirado_por_nome="", sem_retirada=False,
                       visitante_nome="", visitante_motivo="", token=""):
    """Grava a retirada inteira de uma vez. Ou tudo, ou nada.

    Uma transação só porque meia retirada gravada é pior que nenhuma: os pontos
    sairiam sem as peças correspondentes, e ninguém saberia reconstruir o que
    faltou depois que a fila andou.
    """
    visitante_nome = (visitante_nome or "").strip()

    if atendido is None and not visitante_nome:
        raise RetiradaInvalida(
            "Diga de quem é a retirada: escolha o atendido, ou escreva o nome "
            "de quem veio sem cadastro.")

    token = (token or "").strip()
    if token:
        # Reenvio depois de resposta perdida na rede: devolve o mesmo recibo em
        # vez de gravar de novo (ou de acusar a criança pela trava da etapa).
        ja_gravada = Retirada.objects.filter(
            bazar=bazar, token=token, finalizada_em__isnull=False).first()
        if ja_gravada is not None:
            return ja_gravada, ja_gravada.pontos_usados, []

    linhas, total = conferir_pedido(bazar, atendido, pedido, sem_retirada)

    # O alerta de estoque é medido ANTES de gravar. Depois do bulk_create os
    # itens desta retirada já contam como distribuídos, e quem consumisse
    # exatamente o que restava dispararia alerta indevido.
    alertas = estoque_estourado(linhas)

    retirada = Retirada.objects.create(
        bazar=bazar,
        atendido=atendido,
        etapa=bazar.etapa,
        sala=sala,
        sala_do_bazar=sala_do_bazar,
        conferido_por=conferido_por,
        retirado_por=retirado_por,
        retirado_por_nome=retirado_por_nome.strip(),
        cota_no_momento=bazar.cota_inicial,
        token=token,
        sem_retirada=sem_retirada,
        visitante_nome=visitante_nome,
        visitante_motivo=(visitante_motivo or "").strip(),
        finalizada_em=timezone.now(),
    )

    ItemRetirada.objects.bulk_create([
        ItemRetirada(
            retirada=retirada,
            categoria=linha["categoria"],
            quantidade=linha["quantidade"],
            pontos_unitarios=linha["pontos_unitarios"],
            pontos_total=linha["pontos_total"],
        )
        for linha in linhas
    ])

    return retirada, total, alertas


def numeros_do_bazar(bazar):
    """Os números do painel da coordenação, em poucas consultas."""
    from atendido.models import Atendido

    finalizadas = Retirada.objects.filter(
        bazar=bazar, finalizada_em__isnull=False)

    por_etapa = {
        etapa: finalizadas.filter(etapa=etapa).values("atendido").distinct().count()
        for etapa, _ in Retirada.Etapa.choices
    }

    itens = ItemRetirada.objects.filter(retirada__in=finalizadas)
    agregado = itens.aggregate(
        pecas=Sum("quantidade"), pontos=Sum("pontos_total"))

    return {
        "elegiveis": Atendido.objects.ativos().count(),
        "atendidos": finalizadas.values("atendido").distinct().count(),
        "primeira": por_etapa.get(Retirada.Etapa.PRIMEIRA, 0),
        "segunda": por_etapa.get(Retirada.Etapa.SEGUNDA, 0),
        "pecas": agregado["pecas"] or 0,
        "pontos": agregado["pontos"] or 0,
    }


def por_salinha(bazar):
    """Atendimentos por salinha do projeto — a salinha vem da ficha do atendido.

    Devolve TODAS as salas, inclusive as zeradas: o painel precisa mostrar a
    sala que ainda não veio, que é justamente a informação acionável durante o
    evento.
    """
    from atendido.models import LISTA_SALAS

    contagem = {
        linha["atendido__sala"]: linha["total"]
        for linha in (
            Retirada.objects
            .filter(bazar=bazar, finalizada_em__isnull=False)
            .values("atendido__sala")
            .annotate(total=Count("atendido", distinct=True))
        )
    }
    return [
        {"sala": rotulo, "total": contagem.get(codigo, 0)}
        for codigo, rotulo in LISTA_SALAS
    ]


def cancelar_retirada(retirada, por, motivo):
    """Devolve a retirada ao estado de rascunho.

    Não existe campo de status: `finalizada_em` nulo JÁ é o rascunho que o
    modelo prevê, e a UniqueConstraint tem `condition`, então a trava da etapa
    reabre sozinha. Os itens ficam onde estão — `Categoria.distribuido` só conta
    retirada finalizada, então o estoque volta sem ninguém apagar nada.

    O motivo é obrigatório porque cancelamento sem explicação vira, no fim do
    dia, um número que ninguém sabe defender.
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise RetiradaInvalida(
            "Escreva o motivo do cancelamento. Sem ele, o número do fim do dia "
            "fica sem explicação.")
    if retirada.finalizada_em is None:
        raise RetiradaInvalida("Esta retirada já estava cancelada.")

    retirada.finalizada_em = None
    retirada.cancelada_em = timezone.now()
    retirada.cancelada_por = por
    retirada.motivo_cancelamento = motivo
    retirada.save(update_fields=["finalizada_em", "cancelada_em",
                                 "cancelada_por", "motivo_cancelamento"])
    return retirada
