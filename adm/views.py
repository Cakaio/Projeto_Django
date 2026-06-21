from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse
from functools import wraps
from .models import Categoria, Lancamento
from .forms import CategoriaForm, LancamentoForm

AREAS_LEITURA = {'ADM/FIN', 'TRIADE'}
AREAS_ESCRITA = {'ADM/FIN'}


class AdmAcessoMixin(LoginRequiredMixin):
    """Leitura: ADM/FIN, TRIADE, superuser."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_LEITURA):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AdmEscritaMixin(LoginRequiredMixin):
    """Escrita: ADM/FIN, superuser."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_ESCRITA):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def adm_acesso_required(view_func):
    """Decorator para function-based views de leitura ADM."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_LEITURA):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def adm_escrita_required(view_func):
    """Decorator para function-based views de escrita ADM."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_ESCRITA):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def painel(request): return HttpResponse('painel')
def lista_lancamentos(request): return HttpResponse('lancamentos')
def criar_lancamento(request): return HttpResponse('criar')
def editar_lancamento(request, pk): return HttpResponse('editar')
def deletar_lancamento(request, pk): return HttpResponse('deletar')


@adm_acesso_required
def lista_categorias(request):
    categorias = Categoria.objects.all()
    return render(request, 'lista_categorias.html', {'categorias': categorias})


@adm_escrita_required
def criar_categoria(request):
    form = CategoriaForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Categoria criada com sucesso!')
        return redirect('adm:lista_categorias')
    return render(request, 'form_categoria.html', {'form': form, 'titulo': 'Nova Categoria'})


@adm_escrita_required
def editar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    form = CategoriaForm(request.POST or None, instance=categoria)
    if form.is_valid():
        form.save()
        messages.success(request, 'Categoria atualizada!')
        return redirect('adm:lista_categorias')
    return render(request, 'form_categoria.html', {'form': form, 'titulo': 'Editar Categoria', 'objeto': categoria})


@adm_escrita_required
def deletar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        try:
            categoria.delete()
            messages.success(request, 'Categoria removida.')
        except Exception:
            messages.error(request, 'Não é possível remover: existem lançamentos vinculados.')
        return redirect('adm:lista_categorias')
    return render(request, 'form_categoria.html', {'objeto': categoria, 'confirmar_delecao': True, 'titulo': 'Remover Categoria'})


def fluxo_caixa(request): return HttpResponse('fluxo')
def dre(request): return HttpResponse('dre')
