from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from voluntario.models import Grupo

from .forms import ComentarioPautaForm, PautaForm
from .models import CienciaPauta, Pauta


def _ids_grupos_do_usuario(usuario):
    return [
        grupo.pk
        for grupo in Grupo.objects.all()
        if grupo.voluntarios().filter(pk=usuario.pk).exists()
    ]


def _usuario_pertence_ao_grupo(usuario, grupo):
    return grupo.voluntarios().filter(pk=usuario.pk).exists()


@login_required
def criar_pauta(request):
    form = PautaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        pauta = form.save(commit=False)
        pauta.criado_por = request.user
        pauta.emitido_por_area = request.user.area
        pauta.save()
        messages.success(request, "Pauta criada e direcionada ao grupo.")
        return redirect("gerenciamento:pautas")
    return render(request, "gerenciamento/criar_pauta.html", {"form": form})


@login_required
def minhas_pautas(request):
    pautas_da_area = (
        Pauta.objects.filter(emitido_por_area=request.user.area)
        .select_related("grupo", "criado_por")
        .prefetch_related("comentarios")
    )
    return render(request, "gerenciamento/minhas_pautas.html", {
        "pautas": pautas_da_area,
        "totais": {
            "a_fazer": pautas_da_area.filter(status="A_FAZER").count(),
            "em_execucao": pautas_da_area.filter(status="EM_EXECUCAO").count(),
            "finalizadas": pautas_da_area.filter(status="FINALIZADA").count(),
        },
    })


@login_required
def editar_pauta(request, pk):
    pauta = get_object_or_404(Pauta, pk=pk)
    if pauta.emitido_por_area != request.user.area:
        messages.error(request, "Somente a área emissora pode editar esta pauta.")
        return redirect("gerenciamento:minhas_pautas")

    form = PautaForm(request.POST or None, instance=pauta)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Pauta atualizada.")
        return redirect("gerenciamento:minhas_pautas")
    return render(request, "gerenciamento/criar_pauta.html", {
        "form": form,
        "pauta": pauta,
    })


@login_required
def pautas(request):
    grupos_ids = _ids_grupos_do_usuario(request.user)
    mostrar_ocultas = request.GET.get("ocultas") == "1"
    estados = CienciaPauta.objects.filter(voluntario=request.user)
    ocultadas_ids = estados.filter(ocultada=True).values_list("pauta_id", flat=True)
    pautas_usuario = (
        Pauta.objects.filter(grupo_id__in=grupos_ids)
        .select_related("grupo", "criado_por")
        .prefetch_related("comentarios", "comentarios__autor")
    )
    if mostrar_ocultas:
        pautas_usuario = pautas_usuario.filter(pk__in=ocultadas_ids)
    else:
        pautas_usuario = pautas_usuario.exclude(pk__in=ocultadas_ids)

    ciencias_ids = set(estados.values_list("pauta_id", flat=True))
    pautas_usuario = list(pautas_usuario)
    for pauta in pautas_usuario:
        pauta.usuario_ciente = pauta.pk in ciencias_ids

    return render(request, "gerenciamento/pautas.html", {
        "pautas": pautas_usuario,
        "grupos_do_usuario": Grupo.objects.filter(pk__in=grupos_ids),
        "comentario_form": ComentarioPautaForm(),
        "mostrar_ocultas": mostrar_ocultas,
        "total_ocultas": estados.filter(ocultada=True, pauta__grupo_id__in=grupos_ids).count(),
    })


@login_required
def alternar_ciencia_pauta(request, pk):
    pauta = get_object_or_404(Pauta.objects.select_related("grupo"), pk=pk)
    if request.method != "POST" or not _usuario_pertence_ao_grupo(request.user, pauta.grupo):
        messages.error(request, "Você não pode alterar esta pauta.")
        return redirect("gerenciamento:pautas")

    estado, _ = CienciaPauta.objects.get_or_create(pauta=pauta, voluntario=request.user)
    acao = request.POST.get("acao")
    if acao == "ocultar":
        estado.ocultada = True
        estado.ocultada_em = timezone.now()
        estado.save(update_fields=["ocultada", "ocultada_em"])
        messages.success(request, "Pauta marcada como ciente e ocultada do seu quadro.")
    elif acao == "restaurar":
        estado.ocultada = False
        estado.ocultada_em = None
        estado.save(update_fields=["ocultada", "ocultada_em"])
        messages.success(request, "Pauta restaurada no seu quadro.")
    else:
        messages.success(request, "Ciência registrada.")
    return redirect(
        f"{reverse('gerenciamento:pautas')}?ocultas=1"
        if request.POST.get("origem") == "ocultas"
        else "gerenciamento:pautas"
    )


@login_required
def comentar_pauta(request, pk):
    pauta = get_object_or_404(Pauta.objects.select_related("grupo"), pk=pk)
    if request.method != "POST" or not _usuario_pertence_ao_grupo(request.user, pauta.grupo):
        messages.error(request, "Você não pode comentar nesta pauta.")
        return redirect("gerenciamento:pautas")

    form = ComentarioPautaForm(request.POST)
    if form.is_valid():
        comentario = form.save(commit=False)
        comentario.pauta = pauta
        comentario.autor = request.user
        comentario.save()
        messages.success(request, "Comentário adicionado.")
    else:
        messages.error(request, "Escreva um comentário válido.")
    return redirect("gerenciamento:pautas")
