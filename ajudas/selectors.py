from collections import Counter, defaultdict
from datetime import time

from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from sabado.models import DisponibilidadeVoluntario
from semanario.models import LISTA_SALAS, Semanario
from voluntario.models import LISTA_AREAS, Voluntario
from .models import Ajuda, EscalaAjuda
from .validators import sobrepoe


AREAS_OPERACIONAIS = {area for area, _ in LISTA_SALAS} | {"MARKETING", "RECREACAO", "SUPPLY"}


def disponibilidades_confirmadas(sabado):
    return DisponibilidadeVoluntario.objects.filter(
        sabado=sabado, vai_ao_projeto=True, voluntario__in=Voluntario.objects.ativos()
    ).select_related("voluntario").order_by("voluntario__first_name", "voluntario__last_name", "voluntario__username")


def sugerir_necessidades(sabado, disponibilidades):
    proprios = Counter(d.voluntario.area for d in disponibilidades)
    vagas = dict(Semanario.objects.filter(data=sabado).values_list("sala", "vagas"))
    resultado = []
    for area, _ in LISTA_AREAS:
        if area not in AREAS_OPERACIONAIS:
            continue
        inicio, fim = time(9), time(11)
        if area == "SUPPLY":
            inicio, fim = time(6), time(7)
        elif area == "RECREACAO":
            inicio, fim = time(11), time(12, 30)
        inicio, fim = max(inicio, sabado.hora_inicio), min(fim, sabado.hora_fim)
        if inicio >= fim:
            continue
        if area in vagas:
            quantidade = proprios[area] + vagas[area]
            origem = f"{proprios[area]} da área + {vagas[area]} vagas extras do semanário"
        else:
            quantidade = max(proprios[area], 1)
            origem = "Equipe confirmada; revise a quantidade necessária"
        resultado.append({"area": area, "hora_inicio": inicio.strftime("%H:%M"),
                          "hora_fim": fim.strftime("%H:%M"), "quantidade": quantidade,
                          "sugestao": origem})
    return sorted(resultado, key=lambda n: n["hora_inicio"])


def historico_recente(sabado, voluntario_ids):
    historico = defaultdict(list)
    qs = Ajuda.objects.filter(
        voluntario_id__in=voluntario_ids, escala__status=EscalaAjuda.Status.PUBLICADA,
        escala__sabado__data__lt=min(sabado.data, timezone.localdate()),
    ).annotate(posicao=Window(
        expression=RowNumber(), partition_by=[F("voluntario_id")],
        order_by=[F("escala__sabado__data").desc(), F("hora_inicio").desc(), F("pk").desc()],
    )).filter(posicao__lte=5).select_related("escala__sabado").order_by(
        "voluntario_id", "-escala__sabado__data", "-hora_inicio", "-pk")
    for ajuda in qs:
        historico[ajuda.voluntario_id].append({
            "data": ajuda.sabado.data.strftime("%d/%m/%Y"), "area": ajuda.get_area_destino_display(),
            "horario": f"{ajuda.hora_inicio:%H:%M}–{ajuda.hora_fim:%H:%M}",
        })
    return historico


def dados_quadro(sabado):
    escala = EscalaAjuda.objects.filter(sabado=sabado).first()
    disponibilidades = list(disponibilidades_confirmadas(sabado).prefetch_related("pode_ajudar"))
    ajudas = list(escala.ajudas.select_related("voluntario")) if escala else []
    historico = historico_recente(sabado, [d.voluntario_id for d in disponibilidades])
    voluntarios = [{
        "id": d.voluntario_id, "nome": str(d.voluntario), "area": d.voluntario.area,
        "vai_de_carro": d.vai_de_carro, "historico": historico[d.voluntario_id], "apto": True,
        "preferencias": [str(f) for f in d.pode_ajudar.all()],
    } for d in disponibilidades]
    # Uma presença revogada deve ser corrigível pela Tríade, sem apagar a ajuda
    # silenciosamente nem continuar contando a pessoa como disponível.
    ids = {v["id"] for v in voluntarios}
    for ajuda in ajudas:
        if ajuda.voluntario_id not in ids:
            voluntarios.append({"id": ajuda.voluntario_id, "nome": str(ajuda.voluntario),
                                "area": ajuda.voluntario.area, "apto": False,
                                "vai_de_carro": None, "historico": [], "preferencias": []})
            ids.add(ajuda.voluntario_id)
    necessidades = [{"area": n.area, "hora_inicio": n.hora_inicio.strftime("%H:%M"),
                     "hora_fim": n.hora_fim.strftime("%H:%M"), "quantidade": n.quantidade}
                    for n in escala.necessidades.all()] if escala else sugerir_necessidades(sabado, disponibilidades)
    return {"revisao": escala.revisao if escala else 0,
            "status": escala.status if escala else EscalaAjuda.Status.RASCUNHO,
            "hora_inicio": sabado.hora_inicio.strftime("%H:%M"), "hora_fim": sabado.hora_fim.strftime("%H:%M"),
            "areas": [{"valor": valor, "nome": nome} for valor, nome in LISTA_AREAS],
            "voluntarios": voluntarios, "necessidades": necessidades,
            "ajudas": [{"voluntario": a.voluntario_id, "area_destino": a.area_destino,
                        "hora_inicio": a.hora_inicio.strftime("%H:%M"), "hora_fim": a.hora_fim.strftime("%H:%M")}
                       for a in ajudas]}


def cobertura_necessidade(necessidade, voluntarios, ajudas):
    """Divide o período nas mudanças de equipe; não conta presença parcial como integral."""
    inicio, fim = necessidade.hora_inicio, necessidade.hora_fim
    relevantes = [a for a in ajudas if sobrepoe(inicio, fim, a.hora_inicio, a.hora_fim)]
    limites = sorted({inicio, fim} | {max(inicio, a.hora_inicio) for a in relevantes}
                     | {min(fim, a.hora_fim) for a in relevantes})
    segmentos = []
    for esquerda, direita in zip(limites, limites[1:]):
        presentes, extras = [], []
        destinos = {a.voluntario_id: a.area_destino for a in relevantes
                    if sobrepoe(esquerda, direita, a.hora_inicio, a.hora_fim)}
        for v in voluntarios:
            destino = destinos.get(v.pk, v.area)
            if destino == necessidade.area:
                (presentes if v.area == necessidade.area else extras).append(v)
        total = len(presentes) + len(extras)
        segmento = {"hora_inicio": esquerda, "hora_fim": direita,
                    "proprios": presentes, "extras": extras, "total": total,
                    "faltam": max(0, necessidade.quantidade - total),
                    "excesso": max(0, total - necessidade.quantidade)}
        if segmentos and segmentos[-1]["proprios"] == presentes and segmentos[-1]["extras"] == extras:
            segmentos[-1]["hora_fim"] = direita
        else:
            segmentos.append(segmento)
    return segmentos


def quadro_publicado(escala):
    voluntarios = [d.voluntario for d in disponibilidades_confirmadas(escala.sabado)]
    ajudas = list(escala.ajudas.select_related("voluntario"))
    return [{"necessidade": n, "segmentos": cobertura_necessidade(n, voluntarios, ajudas)}
            for n in escala.necessidades.all()]


def card_inicio(usuario):
    escala = EscalaAjuda.objects.filter(status=EscalaAjuda.Status.PUBLICADA,
        sabado__data__gte=timezone.localdate()).select_related("sabado").order_by("sabado__data").first()
    if not escala or not disponibilidades_confirmadas(escala.sabado).filter(voluntario=usuario).exists():
        return None
    ajudas = list(escala.ajudas.filter(voluntario=usuario).order_by("hora_inicio"))
    if not ajudas:
        return None
    return {"sabado": escala.sabado, "principal": ajudas[0], "outras": ajudas[1:], "total": len(ajudas)}
