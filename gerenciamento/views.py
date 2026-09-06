from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max, Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from voluntario.models import Grupo

from .forms import ComentarioPautaForm, PautaForm, ReuniaoForm
from .models import CienciaPauta, ComentarioPauta, Pauta, Reuniao
from .services import (
    ids_grupos_do_usuario,
    pautas_acessiveis_ao_usuario,
    reunioes_acessiveis_ao_usuario,
    usuario_pode_acessar_pauta,
    usuario_pode_acessar_reuniao,
)


STATUS_CORES = {
    Pauta.Status.A_DISCUTIR: "#d97706",
    Pauta.Status.EM_DISCUSSAO: "#7c3aed",
    Pauta.Status.CONCLUIDA: "#16845b",
}


def _url_do_quadro(*, pauta_id=None):
    parametros = {}
    if pauta_id:
        parametros["pauta"] = pauta_id
    url = reverse("gerenciamento:pautas")
    return f"{url}?{urlencode(parametros)}" if parametros else url


def _pode_mover_pauta(usuario, pauta):
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
        usuario.is_superuser
        or pauta.emitido_por_area == getattr(usuario, "area", None)
        or usuario_responsavel
    )


def _dados_progresso_reuniao(pautas):
    total = len(pautas)
    concluidas = sum(
        pauta.status == Pauta.Status.CONCLUIDA for pauta in pautas
    )
    percentual = round((concluidas / total) * 100) if total else 0
    return total, concluidas, percentual


def _ajustar_ordem_reuniao(pauta, *, reuniao_anterior_id=None):
    if not pauta.reuniao_id:
        if pauta.ordem_reuniao:
            pauta.ordem_reuniao = 0
            pauta.save(update_fields=["ordem_reuniao", "atualizado_em"])
        return
    if reuniao_anterior_id == pauta.reuniao_id and pauta.ordem_reuniao:
        return
    ultima_ordem = (
        Pauta.objects.filter(reuniao_id=pauta.reuniao_id)
        .exclude(pk=pauta.pk)
        .aggregate(maior=Max("ordem_reuniao"))["maior"]
        or 0
    )
    pauta.ordem_reuniao = ultima_ordem + 1
    pauta.save(update_fields=["ordem_reuniao", "atualizado_em"])


@login_required
def criar_pauta(request):
    form = PautaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        pauta = form.save(commit=False)
        pauta.criado_por = request.user
        pauta.emitido_por_area = request.user.area
        pauta.save()
        form.save_m2m()
        _ajustar_ordem_reuniao(pauta)
        messages.success(request, "Pauta criada e direcionada ao grupo.")
        return redirect("gerenciamento:pautas")
    return render(request, "gerenciamento/criar_pauta.html", {"form": form})


@login_required
def minhas_pautas(request):
    pautas_da_area = (
        Pauta.objects.filter(emitido_por_area=request.user.area)
        .select_related("grupo", "criado_por", "reuniao")
        .prefetch_related("comentarios", "responsaveis")
    )
    resumo_status = [
        {
            "codigo": codigo,
            "titulo": titulo,
            "total": pautas_da_area.filter(status=codigo).count(),
            "cor": STATUS_CORES[codigo],
        }
        for codigo, titulo in Pauta.Status.choices
    ]
    return render(request, "gerenciamento/minhas_pautas.html", {
        "pautas": pautas_da_area,
        "resumo_status": resumo_status,
    })


@login_required
def editar_pauta(request, pk):
    pauta = get_object_or_404(Pauta, pk=pk)
    if not _pode_mover_pauta(request.user, pauta):
        messages.error(request, "Somente a área emissora ou os responsáveis podem editar esta pauta.")
        return redirect("gerenciamento:minhas_pautas")

    reuniao_anterior_id = pauta.reuniao_id
    form = PautaForm(request.POST or None, instance=pauta)
    if request.method == "POST" and form.is_valid():
        pauta = form.save()
        _ajustar_ordem_reuniao(
            pauta,
            reuniao_anterior_id=reuniao_anterior_id,
        )
        messages.success(request, "Pauta atualizada.")
        return redirect("gerenciamento:minhas_pautas")
    return render(request, "gerenciamento/criar_pauta.html", {
        "form": form,
        "pauta": pauta,
    })


@login_required
def pautas(request):
    grupos_ids = ids_grupos_do_usuario(request.user)
    estados = CienciaPauta.objects.filter(voluntario=request.user)

    comentarios = (
        ComentarioPauta.objects
        .select_related("autor")
        .prefetch_related("mencoes")
    )
    pautas_usuario = (
        pautas_acessiveis_ao_usuario(request.user)
        .select_related("grupo", "criado_por", "reuniao")
        .prefetch_related(
            "responsaveis",
            Prefetch("comentarios", queryset=comentarios),
        )
    )

    ciencias_ids = set(estados.values_list("pauta_id", flat=True))
    agora = timezone.now()
    colunas = [
        {
            "codigo": codigo,
            "titulo": titulo,
            "cor": STATUS_CORES[codigo],
            "pautas": [],
        }
        for codigo, titulo in Pauta.Status.choices
    ]
    colunas_por_codigo = {coluna["codigo"]: coluna for coluna in colunas}

    pautas_usuario = list(pautas_usuario)
    for pauta in pautas_usuario:
        pauta.usuario_ciente = pauta.pk in ciencias_ids
        pauta.pode_mover = _pode_mover_pauta(request.user, pauta)
        pauta.atrasada = (
            pauta.status != Pauta.Status.CONCLUIDA
            and pauta.prazo_ddl < agora
        )
        coluna = colunas_por_codigo.get(pauta.status)
        if coluna:
            coluna["pautas"].append(pauta)

    usuarios_mencao = [
        {
            "username": usuario.username,
            "nome": usuario.get_full_name() or usuario.username,
        }
        for usuario in (
            get_user_model().objects.ativos()
            .order_by("first_name", "last_name", "username")
        )
    ]

    pauta_aberta_id = request.GET.get("pauta", "")
    if not pauta_aberta_id.isdigit() or not any(
        pauta.pk == int(pauta_aberta_id) for pauta in pautas_usuario
    ):
        pauta_aberta_id = ""

    return render(request, "gerenciamento/pautas.html", {
        "colunas": colunas,
        "pautas": pautas_usuario,
        "status_choices": Pauta.Status.choices,
        "grupos_do_usuario": Grupo.objects.filter(pk__in=grupos_ids),
        "usuarios_mencao": usuarios_mencao,
        "pauta_aberta_id": pauta_aberta_id,
    })


@login_required
@require_POST
def registrar_ciencia_pauta(request, pk):
    pauta = get_object_or_404(
        Pauta.objects.select_related("grupo").prefetch_related("responsaveis"),
        pk=pk,
    )
    if not usuario_pode_acessar_pauta(request.user, pauta):
        messages.error(request, "Você não pode alterar esta pauta.")
        return redirect("gerenciamento:pautas")

    _, criada = CienciaPauta.objects.get_or_create(
        pauta=pauta,
        voluntario=request.user,
    )
    if criada:
        messages.success(request, "Ciência registrada.")
    else:
        messages.info(request, "Sua ciência já estava registrada.")

    return redirect(_url_do_quadro(pauta_id=pauta.pk))


@login_required
@require_POST
def comentar_pauta(request, pk):
    pauta = get_object_or_404(
        Pauta.objects.select_related("grupo").prefetch_related("responsaveis"),
        pk=pk,
    )
    if not usuario_pode_acessar_pauta(request.user, pauta):
        messages.error(request, "Você não pode comentar nesta pauta.")
        return redirect("gerenciamento:pautas")

    form = ComentarioPautaForm(request.POST)
    if form.is_valid():
        comentario = form.save(commit=False)
        comentario.pauta = pauta
        comentario.autor = request.user
        comentario.save()
        total_mencoes = comentario.mencoes.count()
        complemento = (
            f" {total_mencoes} menção registrada."
            if total_mencoes == 1
            else f" {total_mencoes} menções registradas."
            if total_mencoes > 1
            else ""
        )
        messages.success(request, f"Comentário adicionado.{complemento}")
    else:
        messages.error(request, "Escreva um comentário válido de até 2.000 caracteres.")
    return redirect(_url_do_quadro(pauta_id=pauta.pk))


@login_required
@require_POST
def atualizar_status_pauta(request, pk):
    pauta = get_object_or_404(Pauta, pk=pk)
    resposta_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not _pode_mover_pauta(request.user, pauta):
        if resposta_json:
            return JsonResponse({"erro": "Você não pode mover esta pauta."}, status=403)
        messages.error(request, "Somente a área emissora ou os responsáveis podem mover esta pauta.")
        return redirect("gerenciamento:pautas")

    novo_status = request.POST.get("status")
    status_validos = dict(Pauta.Status.choices)
    if novo_status not in status_validos:
        if resposta_json:
            return JsonResponse({"erro": "Status inválido."}, status=400)
        messages.error(request, "Escolha uma coluna válida.")
        return redirect(_url_do_quadro(pauta_id=pauta.pk))

    with transaction.atomic():
        pauta = Pauta.objects.select_for_update().get(pk=pauta.pk)
        if pauta.status != novo_status:
            ultima_ordem = (
                Pauta.objects.filter(grupo=pauta.grupo, status=novo_status)
                .aggregate(maior=Max("ordem"))["maior"]
                or 0
            )
            pauta.status = novo_status
            pauta.ordem = ultima_ordem + 1
            pauta.save(update_fields=["status", "ordem", "atualizado_em"])

    if resposta_json:
        return JsonResponse({
            "ok": True,
            "status": pauta.status,
            "status_label": pauta.get_status_display(),
            "status_cor": pauta.status_cor,
            "atrasada": (
                pauta.status != Pauta.Status.CONCLUIDA
                and pauta.prazo_ddl < timezone.now()
            ),
            "proximo_status": pauta.proximo_status,
            "proximo_status_label": (
                dict(Pauta.Status.choices).get(pauta.proximo_status)
                if pauta.proximo_status
                else None
            ),
        })

    messages.success(request, f"Pauta movida para “{pauta.get_status_display()}”.")
    if request.POST.get("retorno") == "painel_reuniao" and pauta.reuniao_id:
        return redirect("gerenciamento:painel_reuniao", pk=pauta.reuniao_id)
    return redirect(_url_do_quadro(pauta_id=pauta.pk))


@login_required
def criar_reuniao(request):
    form = ReuniaoForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        ids_selecionados = [
            pauta.pk for pauta in form.pautas_selecionadas
        ]
        try:
            with transaction.atomic():
                pautas_bloqueadas = list(
                    Pauta.objects.select_for_update()
                    .filter(pk__in=ids_selecionados, reuniao__isnull=True)
                )
                if len(pautas_bloqueadas) != len(ids_selecionados):
                    raise ValidationError(
                        "Uma pauta acabou de ser vinculada a outra reunião. Atualize a seleção."
                    )
                if any(
                    pauta.grupo_id != form.cleaned_data["grupo"].pk
                    for pauta in pautas_bloqueadas
                ):
                    raise ValidationError(
                        "Todas as pautas precisam permanecer no grupo da reunião."
                    )

                reuniao = form.save()
                por_id = {pauta.pk: pauta for pauta in pautas_bloqueadas}
                for ordem, pauta_id in enumerate(ids_selecionados, start=1):
                    pauta = por_id[pauta_id]
                    pauta.reuniao = reuniao
                    pauta.ordem_reuniao = ordem
                Pauta.objects.bulk_update(
                    pautas_bloqueadas,
                    ["reuniao", "ordem_reuniao"],
                )
        except ValidationError as erro:
            form.add_error(None, erro.message)
        else:
            messages.success(request, "Reunião montada. O painel já está pronto para apresentar.")
            return redirect("gerenciamento:painel_reuniao", pk=reuniao.pk)

    reunioes_recentes = (
        reunioes_acessiveis_ao_usuario(request.user)
        .select_related("grupo")
        .prefetch_related("pautas")
        .order_by("-data_reuniao")[:6]
    )
    return render(request, "gerenciamento/criar_reuniao.html", {
        "form": form,
        "pautas_disponiveis": form.pautas_disponiveis,
        "reunioes_recentes": reunioes_recentes,
    })


@login_required
def painel_reuniao(request, pk):
    reuniao = get_object_or_404(Reuniao.objects.select_related("grupo"), pk=pk)
    if not usuario_pode_acessar_reuniao(request.user, reuniao):
        raise PermissionDenied

    pautas = list(
        reuniao.pautas
        .select_related("criado_por", "grupo")
        .prefetch_related("responsaveis", "comentarios__autor")
        .order_by("ordem_reuniao", "prazo_ddl", "pk")
    )
    for pauta in pautas:
        pauta.pode_mover = _pode_mover_pauta(request.user, pauta)
        pauta.proximo_status_label = (
            dict(Pauta.Status.choices).get(pauta.proximo_status)
            if pauta.proximo_status
            else None
        )

    total, concluidas, percentual = _dados_progresso_reuniao(pautas)
    return render(request, "gerenciamento/painel_reuniao.html", {
        "reuniao": reuniao,
        "pautas": pautas,
        "total_pautas": total,
        "pautas_concluidas": concluidas,
        "percentual_concluido": percentual,
    })


@login_required
@require_GET
@never_cache
def estado_reuniao(request, pk):
    reuniao = get_object_or_404(Reuniao.objects.select_related("grupo"), pk=pk)
    if not usuario_pode_acessar_reuniao(request.user, reuniao):
        return JsonResponse({"erro": "Você não pode acessar esta reunião."}, status=403)

    pautas = list(
        reuniao.pautas.prefetch_related("responsaveis")
        .order_by("ordem_reuniao", "prazo_ddl", "pk")
    )
    total, concluidas, percentual = _dados_progresso_reuniao(pautas)
    status_labels = dict(Pauta.Status.choices)
    return JsonResponse({
        "reuniao_id": reuniao.pk,
        "total": total,
        "concluidas": concluidas,
        "percentual": percentual,
        "pautas": [
            {
                "id": pauta.pk,
                "status": pauta.status,
                "status_label": pauta.get_status_display(),
                "status_cor": pauta.status_cor,
                "proximo_status": pauta.proximo_status,
                "proximo_status_label": status_labels.get(pauta.proximo_status),
                "pode_mover": _pode_mover_pauta(request.user, pauta),
            }
            for pauta in pautas
        ],
    })
