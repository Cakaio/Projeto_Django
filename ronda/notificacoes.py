"""Textos da notificação de ronda — pedido 4.

Separado da view pelo mesmo motivo de `ronda/sorteio.py`: montar o texto é a
parte que erra (horário nulo em dia de evento, pessoa em dois locais, corpo
estourando o limite do aparelho), e precisa de teste direto. O test client do
Django quebra ao renderizar template neste ambiente, então a suíte chama estas
funções sem passar por HTTP.
"""
from collections import defaultdict

from .models import EscalaRonda

# A notificação da ronda não é sensível: a escala é pública para todo voluntário
# em /ronda/sabado/. Por isso o título pode ser explícito — diferente do push de
# ocorrência, que é genérico de propósito porque aparece na tela de bloqueio.
TITULO = "Você está na ronda"

# O corpo é cortado pelo aparelho bem antes disso; 300 é o limite que o projeto
# já adota em Aviso.mensagem. Truncar aqui é melhor que deixar o Android cortar
# no meio do nome do local.
LIMITE_CORPO = 300

URL_RONDA = "/ronda/sabado/"


def escalas_da_configuracao(cfg):
    """Todas as escalas da ronda, numa query só.

    `select_related` de voluntario e horario__local porque o texto usa os três —
    sem isso cada escala custaria três queries a mais, e a mesma lista serve ao
    ScoreRonda na view de aprovação.

    Ordena por horário e local para o texto sair na ordem em que a pessoa vai
    cumprir a escala.
    """
    return list(
        EscalaRonda.objects
        .filter(horario__configuracao=cfg)
        .select_related('voluntario', 'horario', 'horario__local')
        .order_by('horario__hora_inicio', 'horario__local__nome')
    )


def _trecho_normal(escala):
    """"08:00–09:00 · Portão" — ou só o local, se o horário não foi preenchido.

    Nunca usa `str(horario)`: `HorarioRonda.__str__` formata a hora sem checar
    None e estoura TypeError quando ela está vazia.
    """
    horario = escala.horario
    local = horario.local.nome if horario.local_id else "local a definir"
    if horario.hora_inicio and horario.hora_fim:
        return f"{horario.hora_inicio:%H:%M}–{horario.hora_fim:%H:%M} · {local}"
    return local


def _trecho_evento(escala):
    """"Portão · Dupla 1" — sem horário, que no dia de evento não existe.

    O rótulo vem do local (`rotulo_grupo`), não é fixo: dois locais da mesma
    ronda podem trabalhar em tamanhos diferentes, um em duplas e outro em trios.
    """
    horario = escala.horario
    if not horario.local_id:
        return "local a definir"
    local = horario.local
    if escala.dupla:
        return f"{local.nome} · {local.rotulo_grupo} {escala.dupla}"
    return local.nome


def corpo_para(cfg, escalas_da_pessoa):
    """Texto de uma pessoa, juntando TODAS as escalas dela nesta ronda.

    No modo normal o sorteio só impede repetição dentro da mesma faixa de
    horário, então a mesma pessoa cai em janelas diferentes com frequência — e
    quem tem score baixo cai em várias. Uma notificação por escala mandaria duas
    ou três seguidas para a mesma pessoa; aqui é uma só, com tudo dentro.
    """
    data = cfg.sabado.data.strftime("%d/%m")
    montar = _trecho_evento if cfg.dia_de_evento else _trecho_normal
    trechos = [montar(e) for e in escalas_da_pessoa]

    corpo = f"Sábado {data}: {' | '.join(trechos)}"
    if len(corpo) <= LIMITE_CORPO:
        return corpo

    # Estourou: mostra o que couber e diz quantos ficaram de fora, em vez de
    # deixar o aparelho cortar no meio de um nome.
    mantidos = []
    for trecho in trechos:
        tentativa = f"Sábado {data}: {' | '.join(mantidos + [trecho])}"
        if len(tentativa) > LIMITE_CORPO - 25:
            break
        mantidos.append(trecho)
    restantes = len(trechos) - len(mantidos)
    return f"Sábado {data}: {' | '.join(mantidos)} (+{restantes} no app)"


def mensagens_da_ronda(cfg, escalas=None):
    """[(voluntario, corpo)] — uma entrada por PESSOA, não por escala.

    É o formato que `notificacoes.services.enviar_push_individual` consome:
    corpo diferente por pessoa, num SELECT e numa thread só.
    """
    if escalas is None:
        escalas = escalas_da_configuracao(cfg)

    por_pessoa = defaultdict(list)
    for escala in escalas:
        por_pessoa[escala.voluntario].append(escala)

    return [(voluntario, corpo_para(cfg, suas))
            for voluntario, suas in por_pessoa.items()]
