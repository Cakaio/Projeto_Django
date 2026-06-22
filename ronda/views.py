# ronda/views.py
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from functools import wraps
from django.utils import timezone

from .models import (
    LocalRonda, ConfiguracaoRondaSabado, HorarioRonda,
    ScoreRonda, AREAS_ISENTAS_RONDA,
)
from .forms import (
    LocalRondaForm, ConfiguracaoRondaForm, HorarioRondaFormSet,
)

RONDA_GESTAO = {'TRIADE'}


def ronda_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in RONDA_GESTAO):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


# ── Painel ──────────────────────────────────────────────────────────────────

@ronda_required
def painel(request):
    configuracoes = ConfiguracaoRondaSabado.objects.select_related('sabado', 'criado_por').all()
    return render(request, 'painel_ronda.html', {'configuracoes': configuracoes})


# ── CRUD LocalRonda ──────────────────────────────────────────────────────────

@ronda_required
def locais(request):
    return render(request, 'locais_ronda.html', {'locais': LocalRonda.objects.all()})


@ronda_required
def local_criar(request):
    form = LocalRondaForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Local criado!')
        return redirect('ronda:locais')
    return render(request, 'form_local.html', {'form': form, 'titulo': 'Novo Local de Ronda'})


@ronda_required
def local_editar(request, pk):
    local = get_object_or_404(LocalRonda, pk=pk)
    form = LocalRondaForm(request.POST or None, instance=local)
    if form.is_valid():
        form.save()
        messages.success(request, 'Local atualizado!')
        return redirect('ronda:locais')
    return render(request, 'form_local.html', {'form': form, 'titulo': 'Editar Local', 'objeto': local})


@ronda_required
def local_deletar(request, pk):
    local = get_object_or_404(LocalRonda, pk=pk)
    if request.method == 'POST':
        local.delete()
        messages.success(request, 'Local removido.')
        return redirect('ronda:locais')
    return render(request, 'form_local.html', {'objeto': local, 'confirmar_delecao': True, 'titulo': 'Remover Local'})


# ── Configuração ─────────────────────────────────────────────────────────────

@ronda_required
def configuracao_criar(request):
    form = ConfiguracaoRondaForm(request.POST or None)
    formset = HorarioRondaFormSet(request.POST or None, prefix='horarios')
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        cfg = form.save(commit=False)
        cfg.criado_por = request.user
        cfg.save()
        formset.instance = cfg
        formset.save()
        messages.success(request, 'Configuração criada! Agora você pode sortear.')
        return redirect('ronda:painel')
    return render(request, 'form_configuracao.html', {'form': form, 'formset': formset})
