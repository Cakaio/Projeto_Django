from django.db.models import Q
from django.db import transaction
from django.urls import reverse

from notificacoes.services import enviar_push_async

from voluntario.models import Grupo

from .models import NotificacaoMencaoPauta, Pauta, Reuniao


def notificar_mencoes(comentario, anteriores):
    destinatarios = list(comentario.mencoes.exclude(pk__in=anteriores | {comentario.autor_id}))
    if not destinatarios:
        return
    pauta = Pauta.objects.select_related("grupo").prefetch_related("responsaveis").get(pk=comentario.pauta_id)
    for usuario in destinatarios:
        if not usuario_pode_acessar_pauta(usuario, pauta):
            continue
        notificacao, criada = NotificacaoMencaoPauta.objects.get_or_create(comentario=comentario, destinatario=usuario)
        if criada:
            url = reverse("gerenciamento:pautas") + f"?pauta={pauta.pk}&comentario={comentario.pk}"
            corpo = f"{comentario.autor.get_full_name() or comentario.autor.username} mencionou você em {pauta.titulo}."
            transaction.on_commit(
                lambda usuario=usuario, url=url, corpo=corpo, pk=notificacao.pk: enviar_push_async(
                    [usuario], "Você foi mencionado em uma pauta", corpo[:300], url=url, tag=f"mencao-pauta-{pk}",
                ), robust=True,
            )


def mencoes_acessiveis(usuario):
    return NotificacaoMencaoPauta.objects.filter(
        destinatario=usuario,
        comentario__pauta__in=pautas_acessiveis_ao_usuario(usuario),
    )


def _usuario_ativo(usuario):
    return bool(
        getattr(usuario, "is_authenticated", False)
        and getattr(usuario, "is_active", False)
        and getattr(usuario, "data_saida", None) is None
    )


def usuario_atende_regras_do_grupo(usuario, grupo):
    """Espelha ``Grupo.voluntarios()``, sem executar uma consulta por grupo."""
    if not _usuario_ativo(usuario):
        return False

    for regra in grupo.regras or []:
        areas = regra.get("areas") or []
        cargos = regra.get("cargos") or []
        atende_area = not areas or getattr(usuario, "area", None) in areas
        atende_cargo = not cargos or getattr(usuario, "cargo", None) in cargos
        if atende_area and atende_cargo:
            return True
    return False


def ids_grupos_do_usuario(usuario):
    if not _usuario_ativo(usuario):
        return []
    return [
        grupo.pk
        for grupo in Grupo.objects.only("pk", "regras")
        if usuario_atende_regras_do_grupo(usuario, grupo)
    ]


def usuario_pode_acessar_pauta(usuario, pauta):
    if not getattr(usuario, "is_authenticated", False):
        return False
    responsaveis_em_cache = getattr(pauta, "_prefetched_objects_cache", {}).get(
        "responsaveis"
    )
    if responsaveis_em_cache is None:
        usuario_responsavel = pauta.responsaveis.filter(pk=usuario.pk).exists()
    else:
        usuario_responsavel = any(
            responsavel.pk == usuario.pk for responsavel in responsaveis_em_cache
        )
    return bool(
        usuario_responsavel
        or usuario_atende_regras_do_grupo(usuario, pauta.grupo)
    )


def pautas_acessiveis_ao_usuario(usuario):
    if not getattr(usuario, "is_authenticated", False):
        return Pauta.objects.none()
    grupos_ids = ids_grupos_do_usuario(usuario)
    return Pauta.objects.filter(
        Q(grupo_id__in=grupos_ids) | Q(responsaveis=usuario)
    ).distinct()


def pautas_organizaveis_ao_usuario(usuario):
    """Inclui pautas recebidas e pautas emitidas pela área do organizador."""
    if not getattr(usuario, "is_authenticated", False):
        return Pauta.objects.none()
    if usuario.is_superuser:
        return Pauta.objects.all()
    grupos_ids = ids_grupos_do_usuario(usuario)
    return Pauta.objects.filter(
        Q(grupo_id__in=grupos_ids)
        | Q(responsaveis=usuario)
        | Q(emitido_por_area=getattr(usuario, "area", None))
    ).distinct()


def reunioes_acessiveis_ao_usuario(usuario):
    if not getattr(usuario, "is_authenticated", False):
        return Reuniao.objects.none()
    if usuario.is_superuser:
        return Reuniao.objects.all()
    grupos_ids = ids_grupos_do_usuario(usuario)
    return Reuniao.objects.filter(
        Q(grupo_id__in=grupos_ids)
        | Q(pautas__responsaveis=usuario)
        | Q(pautas__emitido_por_area=getattr(usuario, "area", None))
    ).distinct()


def usuario_pode_acessar_reuniao(usuario, reuniao):
    if not getattr(usuario, "is_authenticated", False):
        return False
    if usuario.is_superuser or usuario_atende_regras_do_grupo(usuario, reuniao.grupo):
        return True
    return reuniao.pautas.filter(
        Q(responsaveis=usuario)
        | Q(emitido_por_area=getattr(usuario, "area", None))
    ).exists()


def pautas_pendentes_de_ciencia(usuario):
    return (
        pautas_acessiveis_ao_usuario(usuario)
        .exclude(ciencias__voluntario=usuario)
        .exclude(status=Pauta.Status.CONCLUIDA)
    )
