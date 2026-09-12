from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Prefetch, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from voluntario.models import Grupo

from .forms import ComentarioPautaForm, MateriaisPautaForm, PautaForm, ReuniaoForm
from .models import CienciaPauta, ComentarioPauta, MaterialPauta, Pauta, Reuniao
from .services import (
    ids_grupos_do_usuario,
    mencoes_acessiveis,
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

# Por quantos dias uma pauta concluída continua no quadro.
#
# Sem corte, a coluna Concluída cresce para sempre e empurra o que importa para
# longe — e cada pauta custa ~12 KB de HTML, porque a página traz um modal
# completo por pauta. Num quadro de 100 pautas isso é 1,2 MB no celular.
# `?concluidas=todas` mostra o histórico inteiro quando alguém precisa.
DIAS_DE_CONCLUIDAS_NO_QUADRO = 30


def _texto_de_busca(pauta):
    """Tudo que a busca do quadro varre, num campo só e em minúsculas.

    Montado no servidor para o filtro do navegador não precisar cavar o DOM de
    cada card — e para achar por etiqueta e por responsável, que não aparecem
    como texto no card.
    """
    partes = [
        pauta.titulo,
        pauta.descricao,
        pauta.grupo.nome if pauta.grupo_id else "",
        pauta.get_prioridade_display(),
        " ".join(str(etiqueta) for etiqueta in (pauta.etiquetas or [])),
    ]
    partes += [
        f"{responsavel.get_full_name()} {responsavel.username}"
        for responsavel in pauta.responsaveis.all()
    ]
    return " ".join(parte for parte in partes if parte).casefold()


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
    materiais_form = MateriaisPautaForm(request.POST if request.method == "POST" else None, request.FILES)
    if request.method == "POST" and all([form.is_valid(), materiais_form.is_valid()]):
        pauta = form.save(commit=False)
        pauta.criado_por = request.user
        pauta.emitido_por_area = request.user.area
        pauta.save()
        form.save_m2m()
        materiais_form.salvar(pauta, request.user)
        _ajustar_ordem_reuniao(pauta)
        messages.success(request, "Pauta criada e direcionada ao grupo.")
        return redirect("gerenciamento:pautas")
    return render(request, "gerenciamento/criar_pauta.html", {"form": form, "materiais_form": materiais_form})


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
    materiais_form = MateriaisPautaForm(request.POST if request.method == "POST" else None, request.FILES)
    if request.method == "POST" and all([form.is_valid(), materiais_form.is_valid()]):
        pauta = form.save()
        materiais_form.salvar(pauta, request.user)
        _ajustar_ordem_reuniao(
            pauta,
            reuniao_anterior_id=reuniao_anterior_id,
        )
        messages.success(request, "Pauta atualizada.")
        return redirect("gerenciamento:minhas_pautas")
    return render(request, "gerenciamento/criar_pauta.html", {
        "form": form,
        "pauta": pauta,
        "materiais_form": materiais_form,
    })


@login_required
def pautas(request, *, materiais_form=None, pauta_material_id=None):
    grupos_ids = ids_grupos_do_usuario(request.user)
    estados = CienciaPauta.objects.filter(voluntario=request.user)

    comentarios = (
        ComentarioPauta.objects
        .select_related("autor")
        .prefetch_related("mencoes")
    )
    pautas_usuario = (
        pautas_acessiveis_ao_usuario(request.user)
        .annotate(total_ciencias=Count("ciencias", distinct=True))
        .select_related("grupo", "criado_por", "reuniao")
        .prefetch_related(
            "responsaveis",
            "materiais",
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

    # Concluída antiga sai do quadro por padrão. É o que impede a terceira
    # coluna de virar um arquivo morto — e o que segura o peso da página, já
    # que cada pauta renderiza um modal inteiro.
    ver_todas_concluidas = request.GET.get("concluidas") == "todas"
    corte_concluidas = agora - timedelta(days=DIAS_DE_CONCLUIDAS_NO_QUADRO)

    pautas_usuario = list(pautas_usuario)
    visiveis = []
    concluidas_ocultas = 0

    for pauta in pautas_usuario:
        antiga = (
            pauta.status == Pauta.Status.CONCLUIDA
            and pauta.atualizado_em < corte_concluidas
        )
        if antiga and not ver_todas_concluidas:
            concluidas_ocultas += 1
            continue

        pauta.materiais_form = materiais_form if pauta.pk == pauta_material_id else MateriaisPautaForm(auto_id=f"material_{pauta.pk}_%s")
        pauta.usuario_ciente = pauta.pk in ciencias_ids
        pauta.pode_mover = _pode_mover_pauta(request.user, pauta)
        pauta.atrasada = (
            pauta.status != Pauta.Status.CONCLUIDA
            and pauta.prazo_ddl < agora
        )
        pauta.sou_responsavel = any(
            responsavel.pk == request.user.pk
            for responsavel in pauta.responsaveis.all()
        )
        pauta.usernames_responsaveis = " ".join(
            responsavel.username for responsavel in pauta.responsaveis.all()
        )
        pauta.texto_de_busca = _texto_de_busca(pauta)

        visiveis.append(pauta)
        coluna = colunas_por_codigo.get(pauta.status)
        if coluna:
            coluna["pautas"].append(pauta)

    pautas_usuario = visiveis

    # Os números que respondem "o que preciso olhar?" sem contar card a card.
    resumo = {
        "total": len(pautas_usuario),
        "atrasadas": sum(1 for pauta in pautas_usuario if pauta.atrasada),
        "sem_ciencia": sum(
            1 for pauta in pautas_usuario
            if not pauta.usuario_ciente and pauta.status != Pauta.Status.CONCLUIDA
        ),
        "minhas": sum(1 for pauta in pautas_usuario if pauta.sou_responsavel),
    }

    # Só quem realmente aparece no quadro entra no filtro: oferecer nome que não
    # devolve resultado nenhum é pior que não oferecer.
    responsaveis_no_quadro = sorted(
        {
            (responsavel.username,
             responsavel.get_full_name() or responsavel.username)
            for pauta in pautas_usuario
            for responsavel in pauta.responsaveis.all()
        },
        key=lambda par: par[1].casefold(),
    )
    grupos_no_quadro = sorted(
        {pauta.grupo.nome for pauta in pautas_usuario if pauta.grupo_id},
        key=str.casefold,
    )

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

    pauta_aberta_id = str(pauta_material_id or request.GET.get("pauta", ""))
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
        "materiais_form": materiais_form or MateriaisPautaForm(),
        "pauta_material_id": pauta_material_id,
        "resumo": resumo,
        "prioridades": Pauta.Prioridade.choices,
        "grupos_no_quadro": grupos_no_quadro,
        "responsaveis_no_quadro": responsaveis_no_quadro,
        "concluidas_ocultas": concluidas_ocultas,
        "ver_todas_concluidas": ver_todas_concluidas,
        "dias_de_concluidas": DIAS_DE_CONCLUIDAS_NO_QUADRO,
    })


@login_required
@require_GET
def ciencias_pauta(request, pk):
    pauta = get_object_or_404(pautas_acessiveis_ao_usuario(request.user), pk=pk)
    ciencias = pauta.ciencias.select_related("voluntario").order_by("voluntario__first_name", "voluntario__last_name", "voluntario__username", "pk")
    busca = request.GET.get("q", "").strip()[:150]
    if busca:
        for termo in busca.split():
            ciencias = ciencias.filter(Q(voluntario__first_name__icontains=termo) | Q(voluntario__last_name__icontains=termo) | Q(voluntario__username__icontains=termo))
    pagina = Paginator(ciencias, 20).get_page(request.GET.get("page"))
    return JsonResponse({
        "total": pagina.paginator.count,
        "proxima": pagina.next_page_number() if pagina.has_next() else None,
        "pessoas": [{"nome": ciencia.voluntario.get_full_name() or ciencia.voluntario.username,
                     "username": ciencia.voluntario.username,
                     "ciente_em": timezone.localtime(ciencia.ciente_em).strftime("%d/%m/%Y às %H:%M")}
                    for ciencia in pagina],
    })


@login_required
@require_POST
def adicionar_materiais(request, pk):
    pauta = get_object_or_404(pautas_acessiveis_ao_usuario(request.user), pk=pk)
    if not _pode_mover_pauta(request.user, pauta):
        raise PermissionDenied
    form = MateriaisPautaForm(request.POST, request.FILES, auto_id=f"material_{pauta.pk}_%s")
    if form.is_valid():
        if form.cleaned_data["documentos"] or form.cleaned_data["links"]:
            form.salvar(pauta, request.user)
            messages.success(request, "Materiais adicionados à pauta.")
            return redirect(_url_do_quadro(pauta_id=pauta.pk))
        form.add_error(None, "Selecione um documento ou informe um link.")
    return pautas(request, materiais_form=form, pauta_material_id=pauta.pk)


@login_required
@require_GET
def baixar_material(request, pk):
    material = get_object_or_404(MaterialPauta.objects.select_related("pauta__grupo").prefetch_related("pauta__responsaveis"), pk=pk)
    if not (usuario_pode_acessar_pauta(request.user, material.pauta) or _pode_mover_pauta(request.user, material.pauta)):
        raise PermissionDenied
    if not material.arquivo:
        raise Http404
    try:
        arquivo = material.arquivo.open("rb")
    except FileNotFoundError:
        raise Http404("Documento indisponível.")
    return FileResponse(arquivo, as_attachment=True, filename=material.nome, content_type="application/octet-stream")


@login_required
def mencoes(request):
    pagina = Paginator(mencoes_acessiveis(request.user).select_related("comentario__autor", "comentario__pauta"), 20).get_page(request.GET.get("page"))
    return render(request, "gerenciamento/mencoes.html", {"pagina": pagina})


@login_required
@require_POST
def ler_mencoes(request, pk):
    pauta = get_object_or_404(pautas_acessiveis_ao_usuario(request.user), pk=pk)
    mencoes_acessiveis(request.user).filter(comentario__pauta=pauta, lida_em__isnull=True).update(lida_em=timezone.now())
    return JsonResponse({"ok": True, "nao_lidas": mencoes_acessiveis(request.user).filter(lida_em__isnull=True).count()})


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
        sem_acesso = sum(not usuario_pode_acessar_pauta(usuario, pauta) for usuario in comentario.mencoes.all())
        if sem_acesso:
            messages.warning(request, f"{sem_acesso} pessoa(s) mencionada(s) não receberam aviso porque não têm acesso à pauta.")
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
