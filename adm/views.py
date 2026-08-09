from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.apps import apps
from functools import wraps
from decimal import Decimal
import csv
from .models import Categoria, Lancamento, ORIGENS_AUTOMATICAS
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


@adm_acesso_required
def painel(request):
    total_receitas = Lancamento.objects.filter(tipo='RECEITA').aggregate(t=Sum('valor'))['t'] or Decimal('0')
    total_despesas = Lancamento.objects.filter(tipo='DESPESA').aggregate(t=Sum('valor'))['t'] or Decimal('0')
    saldo = total_receitas - total_despesas
    ultimos = Lancamento.objects.select_related('categoria').order_by('-data', '-criado_em')[:10]
    PedidoReembolso = apps.get_model('forms_pcf', 'PedidoReembolso')
    reembolsos_pendentes = PedidoReembolso.objects.filter(status='PENDENTE').count()

    return render(request, 'painel_adm.html', {
        'saldo': saldo,
        'total_receitas': total_receitas,
        'total_despesas': total_despesas,
        'ultimos': ultimos,
        'reembolsos_pendentes': reembolsos_pendentes,
    })


@adm_acesso_required
def lista_lancamentos(request):
    qs = Lancamento.objects.select_related('categoria', 'criado_por').all()

    tipo = request.GET.get('tipo')
    categoria_id = request.GET.get('categoria')
    mes = request.GET.get('mes')   # formato YYYY-MM

    if tipo in ('RECEITA', 'DESPESA'):
        qs = qs.filter(tipo=tipo)
    if categoria_id:
        qs = qs.filter(categoria_id=categoria_id)
    if mes:
        try:
            ano, m = mes.split('-')
            qs = qs.filter(data__year=ano, data__month=m)
        except ValueError:
            pass

    categorias = Categoria.objects.filter(ativo=True)
    return render(request, 'lista_lancamentos.html', {
        'lancamentos': qs,
        'categorias': categorias,
        'filtro_tipo': tipo,
        'filtro_categoria': categoria_id,
        'filtro_mes': mes,
    })


@adm_escrita_required
def criar_lancamento(request):
    form = LancamentoForm(request.POST or None)
    if form.is_valid():
        lan = form.save(commit=False)
        lan.origem = 'MANUAL'
        lan.criado_por = request.user
        lan.save()
        messages.success(request, 'Lançamento registrado!')
        return redirect('adm:lista_lancamentos')
    return render(request, 'form_lancamento.html', {'form': form, 'titulo': 'Novo Lançamento'})


@adm_escrita_required
def editar_lancamento(request, pk):
    lan = get_object_or_404(Lancamento, pk=pk)
    if lan.origem in ORIGENS_AUTOMATICAS:
        messages.error(
            request,
            f'Lançamentos com origem "{lan.get_origem_display()}" são gerados automaticamente '
            'e não podem ser editados aqui. Altere o registro de origem.'
        )
        return redirect('adm:lista_lancamentos')
    form = LancamentoForm(request.POST or None, instance=lan)
    if form.is_valid():
        form.save()
        messages.success(request, 'Lançamento atualizado!')
        return redirect('adm:lista_lancamentos')
    return render(request, 'form_lancamento.html', {'form': form, 'titulo': 'Editar Lançamento', 'objeto': lan})


@adm_escrita_required
def deletar_lancamento(request, pk):
    lan = get_object_or_404(Lancamento, pk=pk)
    if lan.origem in ORIGENS_AUTOMATICAS:
        messages.error(
            request,
            f'Lançamentos com origem "{lan.get_origem_display()}" são gerados automaticamente '
            'e não podem ser removidos aqui. Remova o registro de origem.'
        )
        return redirect('adm:lista_lancamentos')
    if request.method == 'POST':
        lan.delete()
        messages.success(request, 'Lançamento removido.')
        return redirect('adm:lista_lancamentos')
    return render(request, 'form_lancamento.html', {
        'objeto': lan, 'confirmar_delecao': True, 'titulo': 'Remover Lançamento'
    })


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
        except ProtectedError:
            messages.error(request, 'Não é possível remover: existem lançamentos vinculados.')
        return redirect('adm:lista_categorias')
    return render(request, 'form_categoria.html', {'objeto': categoria, 'confirmar_delecao': True, 'titulo': 'Remover Categoria'})


@adm_acesso_required
def fluxo_caixa(request):
    qs = Lancamento.objects.select_related('categoria').order_by('data', 'criado_em')

    # Filtros
    tipo = request.GET.get('tipo')
    categoria_id = request.GET.get('categoria')
    data_ini = request.GET.get('data_ini')
    data_fim = request.GET.get('data_fim')
    exportar = request.GET.get('exportar')

    if tipo in ('RECEITA', 'DESPESA'):
        qs = qs.filter(tipo=tipo)
    if categoria_id:
        qs = qs.filter(categoria_id=categoria_id)
    if data_ini:
        qs = qs.filter(data__gte=data_ini)
    if data_fim:
        qs = qs.filter(data__lte=data_fim)

    # Calcular saldo acumulado
    saldo = Decimal('0')
    lancamentos_com_saldo = []
    for lan in qs:
        if lan.tipo == 'RECEITA':
            saldo += lan.valor
        else:
            saldo -= lan.valor
        lancamentos_com_saldo.append({'lan': lan, 'saldo': saldo})

    if exportar == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="fluxo_caixa.csv"'
        response.write('﻿')  # BOM para Excel reconhecer UTF-8
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Data', 'Descrição', 'Categoria', 'Tipo', 'Entrada (R$)', 'Saída (R$)', 'Saldo (R$)'])
        for item in lancamentos_com_saldo:
            lan = item['lan']
            entrada = lan.valor if lan.tipo == 'RECEITA' else ''
            saida = lan.valor if lan.tipo == 'DESPESA' else ''
            writer.writerow([
                lan.data.strftime('%d/%m/%Y'),
                lan.descricao or lan.categoria.nome,
                lan.categoria.nome,
                lan.get_tipo_display(),
                str(entrada).replace('.', ',') if entrada else '',
                str(saida).replace('.', ',') if saida else '',
                str(item['saldo']).replace('.', ','),
            ])
        return response

    categorias = Categoria.objects.filter(ativo=True)
    return render(request, 'fluxo_caixa.html', {
        'lancamentos_com_saldo': lancamentos_com_saldo,
        'saldo_final': saldo,
        'categorias': categorias,
        'filtro_tipo': tipo,
        'filtro_categoria': categoria_id,
        'filtro_data_ini': data_ini,
        'filtro_data_fim': data_fim,
    })


def _calcular_dre(ano, mes):
    """Retorna dict com receitas, despesas e resultado para um mês."""
    qs = Lancamento.objects.filter(data__year=ano, data__month=mes)

    receitas = (
        qs.filter(tipo='RECEITA')
        .values('categoria__nome')
        .annotate(total=Sum('valor'))
        .order_by('categoria__nome')
    )
    despesas = (
        qs.filter(tipo='DESPESA')
        .values('categoria__nome')
        .annotate(total=Sum('valor'))
        .order_by('categoria__nome')
    )

    total_receitas = qs.filter(tipo='RECEITA').aggregate(t=Sum('valor'))['t'] or Decimal('0')
    total_despesas = qs.filter(tipo='DESPESA').aggregate(t=Sum('valor'))['t'] or Decimal('0')

    return {
        'receitas': list(receitas),
        'despesas': list(despesas),
        'total_receitas': total_receitas,
        'total_despesas': total_despesas,
        'resultado': total_receitas - total_despesas,
    }


@adm_acesso_required
def dre(request):
    hoje = timezone.now().date()

    # Período principal
    mes_str = request.GET.get('mes', hoje.strftime('%Y-%m'))
    # Período comparativo
    comp_str = request.GET.get('comparar', '')

    try:
        ano_p, mes_p = [int(x) for x in mes_str.split('-')]
    except (ValueError, AttributeError):
        ano_p, mes_p = hoje.year, hoje.month

    dre_principal = _calcular_dre(ano_p, mes_p)
    dre_comparativo = None
    deltas = None

    if comp_str:
        try:
            ano_c, mes_c = [int(x) for x in comp_str.split('-')]
            dre_comparativo = _calcular_dre(ano_c, mes_c)

            # Construir dicts {categoria_nome: total} para lookup
            rec_p = {r['categoria__nome']: r['total'] for r in dre_principal['receitas']}
            rec_c = {r['categoria__nome']: r['total'] for r in dre_comparativo['receitas']}
            desp_p = {d['categoria__nome']: d['total'] for d in dre_principal['despesas']}
            desp_c = {d['categoria__nome']: d['total'] for d in dre_comparativo['despesas']}

            # Calcular deltas para cada categoria
            deltas = {
                'receitas': {k: rec_p.get(k, Decimal('0')) - rec_c.get(k, Decimal('0'))
                            for k in set(list(rec_p.keys()) + list(rec_c.keys()))},
                'despesas': {k: desp_p.get(k, Decimal('0')) - desp_c.get(k, Decimal('0'))
                            for k in set(list(desp_p.keys()) + list(desp_c.keys()))},
                'resultado': dre_principal['resultado'] - dre_comparativo['resultado'],
            }
        except (ValueError, AttributeError):
            pass

    return render(request, 'dre.html', {
        'dre': dre_principal,
        'dre_comp': dre_comparativo,
        'deltas': deltas,
        'mes': mes_str,
        'comparar': comp_str,
    })


