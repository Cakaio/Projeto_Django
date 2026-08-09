"""Telas do CRM de Parceiros (área CR/RE).

Permissão: CR/RE, Tríade e superusuário — leitura e escrita. Segue o padrão de
decorator por área do app `ronda` (PermissionDenied → 403).
"""
from collections import OrderedDict
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ContribuicaoForm, InteracaoForm, ParceiroForm
from .models import Contribuicao, Interacao, Parceiro

AREAS_CRM = {'CR/RE', 'TRIADE'}

MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
         'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']


def crm_required(view_func):
    """Acesso ao CRM: CR/RE, Tríade ou superusuário."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser
                or getattr(request.user, 'area', None) in AREAS_CRM):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def _ano_selecionado(request):
    try:
        return int(request.GET.get('ano') or timezone.localdate().year)
    except (TypeError, ValueError):
        return timezone.localdate().year


def _anos_disponiveis(ano_atual):
    """Anos que já têm contribuição, mais o ano corrente e o selecionado."""
    anos = {d.year for d in Contribuicao.objects.dates('competencia', 'year')}
    anos.update({ano_atual, timezone.localdate().year})
    return sorted(anos, reverse=True)


# ─────────────────────────── Painel ───────────────────────────
@crm_required
def painel(request):
    ano = _ano_selecionado(request)
    hoje = timezone.localdate()

    do_ano = Contribuicao.objects.filter(competencia__year=ano)
    total_ano = do_ano.aggregate(t=Sum('valor'))['t'] or Decimal('0')
    total_mes = do_ano.filter(competencia__month=hoje.month).aggregate(t=Sum('valor'))['t'] or Decimal('0') \
        if ano == hoje.year else Decimal('0')

    # Série mensal (para as barras) — sempre 12 posições.
    por_mes = {c['competencia__month']: c['t'] for c in
               do_ano.values('competencia__month').annotate(t=Sum('valor'))}
    maior = max(por_mes.values()) if por_mes else Decimal('0')
    serie = [{
        'rotulo': MESES[m - 1],
        'valor': por_mes.get(m, Decimal('0')),
        'altura': int((por_mes.get(m, Decimal('0')) / maior) * 100) if maior else 0,
        'atual': (ano == hoje.year and m == hoje.month),
    } for m in range(1, 13)]

    # Ranking por responsável (a "carteira").
    carteiras = (Parceiro.objects
                 .filter(contribuicoes__competencia__year=ano)
                 .values('responsavel', 'responsavel__first_name',
                         'responsavel__last_name', 'responsavel__username')
                 .annotate(total=Sum('contribuicoes__valor'),
                           parceiros=Count('id', distinct=True))
                 .order_by('-total'))

    parceiros_ativos = Parceiro.objects.filter(status='ATIVO').count()
    doadores_no_ano = do_ano.values('parceiro').distinct().count()

    return render(request, 'parceiros/painel.html', {
        'ano': ano,
        'anos': _anos_disponiveis(ano),
        'total_ano': total_ano,
        'total_mes': total_mes,
        'parceiros_ativos': parceiros_ativos,
        'doadores_no_ano': doadores_no_ano,
        'ticket_medio': (total_ano / doadores_no_ano) if doadores_no_ano else Decimal('0'),
        'serie': serie,
        'carteiras': carteiras,
        'ultimas': (Contribuicao.objects
                    .select_related('parceiro', 'parceiro__responsavel')
                    .order_by('-data_recebimento', '-criado_em')[:8]),
    })


# ─────────────────────── Grade anual (a planilha) ───────────────────────
@crm_required
def grade(request):
    """A planilha: parceiros nas linhas, Jan→Dez nas colunas, totais no rodapé."""
    ano = _ano_selecionado(request)
    responsavel = request.GET.get('responsavel') or ''

    parceiros = (Parceiro.objects
                 .select_related('responsavel')
                 .prefetch_related('contribuicoes')
                 .exclude(status='ENCERRADO'))
    if responsavel == 'minha':
        parceiros = parceiros.filter(responsavel=request.user)
    elif responsavel.isdigit():
        parceiros = parceiros.filter(responsavel_id=int(responsavel))

    totais_mes = [Decimal('0')] * 12
    linhas = []
    for parceiro in parceiros:
        celulas = [None] * 12
        for c in parceiro.contribuicoes.all():
            if c.competencia.year == ano:
                indice = c.competencia.month - 1
                celulas[indice] = c
                totais_mes[indice] += c.valor
        total_linha = sum((c.valor for c in celulas if c), Decimal('0'))
        linhas.append({'parceiro': parceiro, 'celulas': celulas, 'total': total_linha})

    # Só mostra quem teve movimento no ano OU está ativo (evita poluir a grade).
    linhas = [l for l in linhas if l['total'] or l['parceiro'].status == 'ATIVO']

    return render(request, 'parceiros/grade.html', {
        'ano': ano,
        'anos': _anos_disponiveis(ano),
        'meses': MESES,
        'linhas': linhas,
        'totais_mes': totais_mes,
        'total_geral': sum(totais_mes, Decimal('0')),
        'responsavel': responsavel,
        'responsaveis': (Parceiro.objects
                         .exclude(responsavel__isnull=True)
                         .values('responsavel', 'responsavel__first_name',
                                 'responsavel__last_name', 'responsavel__username')
                         .distinct()
                         .order_by('responsavel__first_name')),
    })


# ─────────────────────────── Parceiros ───────────────────────────
@crm_required
def lista(request):
    busca = (request.GET.get('q') or '').strip()
    status = request.GET.get('status') or ''
    responsavel = request.GET.get('responsavel') or ''

    parceiros = Parceiro.objects.select_related('responsavel').annotate(
        total=Sum('contribuicoes__valor'))
    if busca:
        parceiros = parceiros.filter(
            Q(nome__icontains=busca) | Q(email__icontains=busca) | Q(telefone__icontains=busca))
    if status:
        parceiros = parceiros.filter(status=status)
    if responsavel == 'minha':
        parceiros = parceiros.filter(responsavel=request.user)
    elif responsavel.isdigit():
        parceiros = parceiros.filter(responsavel_id=int(responsavel))

    return render(request, 'parceiros/lista.html', {
        'parceiros': parceiros,
        'q': busca,
        'status': status,
        'responsavel': responsavel,
        'status_choices': Parceiro._meta.get_field('status').choices,
        'responsaveis': (Parceiro.objects
                         .exclude(responsavel__isnull=True)
                         .values('responsavel', 'responsavel__first_name',
                                 'responsavel__last_name', 'responsavel__username')
                         .distinct()
                         .order_by('responsavel__first_name')),
    })


@crm_required
def ficha(request, pk):
    parceiro = get_object_or_404(
        Parceiro.objects.select_related('responsavel'), pk=pk)

    # Contribuições agrupadas por ano, para o histórico.
    por_ano = OrderedDict()
    for c in parceiro.contribuicoes.select_related('lancamento').order_by('-competencia'):
        por_ano.setdefault(c.competencia.year, []).append(c)
    historico = [{'ano': ano, 'contribuicoes': itens,
                  'total': sum((i.valor for i in itens), Decimal('0'))}
                 for ano, itens in por_ano.items()]

    form_interacao = InteracaoForm(request.POST or None)
    if request.method == 'POST' and form_interacao.is_valid():
        interacao = form_interacao.save(commit=False)
        interacao.parceiro = parceiro
        interacao.autor = request.user
        interacao.save()
        messages.success(request, 'Interação registrada.')
        return redirect('parceiros:ficha', pk=parceiro.pk)

    return render(request, 'parceiros/ficha.html', {
        'parceiro': parceiro,
        'historico': historico,
        'total_geral': parceiro.total_arrecadado,
        'interacoes': parceiro.interacoes.select_related('autor'),
        'form_interacao': form_interacao,
    })


@crm_required
def parceiro_form(request, pk=None):
    parceiro = get_object_or_404(Parceiro, pk=pk) if pk else None
    form = ParceiroForm(request.POST or None, instance=parceiro)
    if request.method == 'POST' and form.is_valid():
        novo = form.save(commit=False)
        if parceiro is None:
            novo.criado_por = request.user
        novo.save()
        messages.success(request, 'Parceiro salvo.')
        return redirect('parceiros:ficha', pk=novo.pk)
    return render(request, 'parceiros/form_parceiro.html', {
        'form': form, 'parceiro': parceiro,
    })


@crm_required
def parceiro_deletar(request, pk):
    parceiro = get_object_or_404(Parceiro, pk=pk)
    if request.method == 'POST':
        nome = parceiro.nome
        parceiro.delete()   # apaga contribuições e os lançamentos vinculados
        messages.success(request, f'{nome} foi removido do CRM.')
        return redirect('parceiros:lista')
    return render(request, 'parceiros/confirmar_exclusao.html', {'parceiro': parceiro})


# ─────────────────────────── Contribuições ───────────────────────────
@crm_required
def contribuicao_form(request, pk=None):
    contribuicao = get_object_or_404(Contribuicao, pk=pk) if pk else None
    inicial = {}
    if contribuicao is None and request.GET.get('parceiro', '').isdigit():
        inicial['parceiro'] = int(request.GET['parceiro'])
    if contribuicao is None and request.GET.get('mes'):
        inicial['competencia'] = request.GET['mes']

    form = ContribuicaoForm(request.POST or None, instance=contribuicao, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        nova = form.save(commit=False)
        if contribuicao is None:
            nova.registrado_por = request.user
        nova.save()
        messages.success(
            request,
            'Contribuição salva e lançada no Financeiro como doação.'
        )
        return redirect(request.POST.get('voltar') or 'parceiros:grade')
    return render(request, 'parceiros/form_contribuicao.html', {
        'form': form, 'contribuicao': contribuicao,
        'voltar': request.GET.get('voltar', ''),
    })


@crm_required
def contribuicao_deletar(request, pk):
    contribuicao = get_object_or_404(Contribuicao.objects.select_related('parceiro'), pk=pk)
    if request.method == 'POST':
        parceiro_id = contribuicao.parceiro_id
        contribuicao.delete()   # o sinal remove o lançamento do Financeiro
        messages.success(request, 'Contribuição removida (e o lançamento no Financeiro também).')
        return redirect(request.POST.get('voltar') or f'/parceiros/{parceiro_id}/')
    return render(request, 'parceiros/confirmar_exclusao.html', {'contribuicao': contribuicao})
