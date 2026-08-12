"""Telas do backlog da área de Projetos.

Permissão: PROJETOS, Tríade e superusuário — leitura e escrita.

O contexto que cada template recebe está anotado na view; os templates são
escritos à parte (`projetos/backlog.html`, `por_area.html`, `ficha.html`,
`form.html`, `confirmar_exclusao.html`).
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from voluntario.models import LISTA_AREAS, Voluntario

from .forms import DemandaForm, RegistroDemandaForm
from .models import (PRIORIDADES, RETORNO_AREA, STATUS_DEMANDA, Demanda,
                     RegistroDemanda)
from .servicos import anotar_situacao, panorama_por_area, sincronizar_retorno

AREAS_PROJETOS = {'PROJETOS', 'TRIADE'}


def projetos_required(view):
    @wraps(view)
    @login_required(login_url='/login/')
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser
                or getattr(request.user, 'area', None) in AREAS_PROJETOS):
            raise PermissionDenied('Esta área é do time de Projetos.')
        return view(request, *args, **kwargs)
    return wrapper


# ────────────────────────────── Backlog ──────────────────────────────
@projetos_required
def backlog(request):
    """A lista do que está sendo feito, item por item.

    Filtros aceitos: ?area= ?status= ?retorno= ?responsavel= (id, `minha` ou
    `sem`) ?q= (título / o que pediram / o que fizemos) ?travadas=1.

    Contexto: demandas (já com `dias_sem_movimento` e `esta_travada`), total,
    abertas, travadas, esperando, entregues, filtros (area, status, retorno,
    responsavel, q, so_travadas), areas, status_choices, retorno_choices,
    responsaveis, hoje.
    """
    area = request.GET.get('area') or ''
    status = request.GET.get('status') or ''
    retorno = request.GET.get('retorno') or ''
    responsavel = request.GET.get('responsavel') or ''
    busca = (request.GET.get('q') or '').strip()
    so_travadas = request.GET.get('travadas') == '1'

    demandas = Demanda.objects.select_related('responsavel', 'contato_na_area')
    if area:
        demandas = demandas.filter(area=area)
    if status:
        demandas = demandas.filter(status=status)
    if retorno:
        demandas = demandas.filter(retorno=retorno)
    if responsavel == 'minha':
        demandas = demandas.filter(responsavel=request.user)
    elif responsavel == 'sem':
        # Demanda sem dono é a que apodrece — vale poder olhar só para elas.
        demandas = demandas.filter(responsavel__isnull=True)
    elif responsavel.isdigit():
        demandas = demandas.filter(responsavel_id=int(responsavel))
    if busca:
        demandas = demandas.filter(Q(titulo__icontains=busca)
                                   | Q(o_que_pediram__icontains=busca)
                                   | Q(o_que_fizemos__icontains=busca))

    # "Travada" depende da data do último registro: não é coluna, então o corte
    # é em Python — mas com os dias já calculados em lote, não item a item.
    demandas = anotar_situacao(demandas)
    if so_travadas:
        demandas = [d for d in demandas if d.esta_travada]

    # Os números do topo falam do que está na tela: com filtro aplicado, KPI de
    # base inteira brigaria com a lista logo abaixo.
    return render(request, 'projetos/backlog.html', {
        'demandas': demandas,
        'total': len(demandas),
        'abertas': sum(1 for d in demandas if d.aberta),
        'travadas': sum(1 for d in demandas if d.esta_travada),
        'esperando': sum(1 for d in demandas
                         if d.aberta and d.retorno in ('AGUARDANDO', 'NAO_RESPONDE')),
        'entregues': sum(1 for d in demandas if d.status == 'ENTREGUE'),
        'area': area,
        'status': status,
        'retorno': retorno,
        'responsavel': responsavel,
        'q': busca,
        'so_travadas': so_travadas,
        'areas': LISTA_AREAS,
        'status_choices': STATUS_DEMANDA,
        'retorno_choices': RETORNO_AREA,
        'prioridades': PRIORIDADES,
        'responsaveis': (Voluntario.objects
                         .filter(demandas__isnull=False)
                         .distinct()
                         .order_by('first_name', 'username')),
        'hoje': timezone.localdate(),
    })


@projetos_required
def por_area(request):
    """A leitura por área: com quem falamos, quem entregou, quem sumiu.

    Contexto: panorama (uma linha por área), total_areas, areas_sem_contato,
    areas_travadas, hoje.
    """
    panorama = panorama_por_area()
    return render(request, 'projetos/por_area.html', {
        'panorama': panorama,
        'total_areas': len(panorama),
        'areas_sem_contato': sum(1 for l in panorama if l['sem_contato']),
        'areas_travadas': sum(1 for l in panorama if l['travadas']),
        'areas_atendidas': sum(1 for l in panorama if l['total']),
        'hoje': timezone.localdate(),
    })


# ────────────────────────────── Ficha ──────────────────────────────
@projetos_required
def ficha(request, pk):
    """Demanda + histórico + formulário de novo registro (POST aqui mesmo).

    Contexto: demanda, registros, form (RegistroDemandaForm), dias_parada,
    travada.
    """
    demanda = get_object_or_404(
        Demanda.objects.select_related('responsavel', 'contato_na_area', 'criado_por'),
        pk=pk)

    form = RegistroDemandaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        registro = form.save(commit=False)
        registro.demanda = demanda
        registro.autor = request.user      # autoria não se escolhe em formulário
        registro.save()
        if sincronizar_retorno(demanda, registro):
            messages.success(
                request,
                f'Registro salvo. O retorno da área virou '
                f'"{demanda.get_retorno_display()}".')
        else:
            messages.success(request, 'Registro salvo.')
        return redirect('projetos:ficha', pk=demanda.pk)

    return render(request, 'projetos/ficha.html', {
        'demanda': demanda,
        'registros': demanda.registros.select_related('autor'),
        'form': form,
        'dias_parada': demanda.dias_parada,
        'travada': demanda.travada,
    })


# ────────────────────────── Criar / editar ──────────────────────────
def _formulario(request, demanda=None):
    """Contexto do form.html: form, demanda (None quando é nova)."""
    form = DemandaForm(request.POST or None, instance=demanda)
    if request.method == 'POST' and form.is_valid():
        nova = form.save(commit=False)
        if demanda is None:
            nova.criado_por = request.user   # nunca vem do formulário
        nova.save()
        messages.success(request, 'Demanda salva.')
        return redirect('projetos:ficha', pk=nova.pk)
    return render(request, 'projetos/form.html', {'form': form, 'demanda': demanda})


@projetos_required
def criar(request):
    return _formulario(request)


@projetos_required
def editar(request, pk):
    return _formulario(request, get_object_or_404(Demanda, pk=pk))


# ──────────────────────────── Exclusões ────────────────────────────
@projetos_required
def deletar(request, pk):
    """Contexto do confirmar_exclusao.html: demanda, quantos_registros."""
    demanda = get_object_or_404(Demanda, pk=pk)
    if request.method == 'POST':
        titulo = demanda.titulo
        demanda.delete()          # o histórico vai junto (CASCADE)
        messages.success(request, f'"{titulo}" saiu do backlog.')
        return redirect('projetos:backlog')
    return render(request, 'projetos/confirmar_exclusao.html', {
        'demanda': demanda,
        'quantos_registros': demanda.registros.count(),
    })


@projetos_required
def registro_deletar(request, pk):
    """Contexto do confirmar_exclusao.html: registro, demanda."""
    registro = get_object_or_404(RegistroDemanda.objects.select_related('demanda'), pk=pk)
    demanda = registro.demanda
    if request.method == 'POST':
        registro.delete()
        messages.success(request, 'Registro removido do histórico.')
        return redirect('projetos:ficha', pk=demanda.pk)
    return render(request, 'projetos/confirmar_exclusao.html', {
        'registro': registro,
        'demanda': demanda,
    })
