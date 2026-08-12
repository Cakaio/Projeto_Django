"""Telas de editais (área CR/RE).

Permissão: CR/RE, Tríade e superusuário. O robô só sugere; quem decide se o
projeto concorre é gente, e é por isso que status, requisitos, observações e
responsável só mudam por aqui.

Contexto que os templates recebem está anotado em cada view — os templates são
escritos à parte (`editais/lista.html`, `form.html`, `fontes.html`,
`fonte_form.html`, `palavras.html`, `confirmar_exclusao.html`).
"""
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (ConsultaBuscaForm, EditalForm, FonteEditalForm,
                    PalavraChaveForm)
from .models import (STATUS_EDITAL, ConsultaBusca, Edital, FonteEdital,
                     PalavraChave)

AREAS_CRRE = {'CR/RE', 'TRIADE'}


def crre_required(view):
    @wraps(view)
    @login_required(login_url='/login/')
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_CRRE):
            raise PermissionDenied('Esta área é do CR/RE.')
        return view(request, *args, **kwargs)
    return wrapper


# ────────────────────────────── Editais ──────────────────────────────
@crre_required
def lista(request):
    """A caixa de entrada do CR: o que o robô trouxe, do mais relevante para o
    menos. Contexto: editais, contadores, q, status, abertos, hoje, kpis."""
    busca = (request.GET.get('q') or '').strip()
    status = request.GET.get('status') or ''
    so_abertos = request.GET.get('abertos') == '1'
    hoje = timezone.localdate()

    editais = Edital.objects.select_related('fonte', 'responsavel')
    if busca:
        editais = editais.filter(Q(titulo__icontains=busca) | Q(descricao__icontains=busca))
    if status:
        editais = editais.filter(status=status)
    if so_abertos:
        # Edital sem prazo informado continua na lista: não dá para afirmar que
        # fechou, e sumir com ele esconderia oportunidade.
        editais = editais.filter(Q(prazo__isnull=True) | Q(prazo__gte=hoje))

    por_status = dict(Edital.objects.values_list('status').annotate(total=Count('id')))
    contadores = [{'valor': valor, 'rotulo': rotulo, 'total': por_status.get(valor, 0)}
                  for valor, rotulo in STATUS_EDITAL]

    em_analise = ('NOVO', 'AVALIANDO', 'VAMOS_CONCORRER', 'INSCRITO')
    return render(request, 'editais/lista.html', {
        'editais': editais,
        'contadores': contadores,
        'status_choices': STATUS_EDITAL,
        'q': busca,
        'status': status,
        'abertos': so_abertos,
        'hoje': hoje,
        'total': sum(por_status.values()),
        'novos': por_status.get('NOVO', 0),
        'vencendo': Edital.objects.filter(
            status__in=em_analise, prazo__gte=hoje,
            prazo__lte=hoje + timedelta(days=7)).count(),
        'fontes_com_erro': FonteEdital.objects.filter(ativo=True).exclude(ultimo_erro='').count(),
    })


def _salvar_edital(request, edital=None):
    form = EditalForm(request.POST or None, instance=edital)
    if request.method == 'POST' and form.is_valid():
        novo = form.save(commit=False)
        if edital is None:
            novo.origem = 'MANUAL'      # veio de gente, não do robô
        novo.save()
        messages.success(request, 'Edital salvo.')
        return redirect('editais:lista')
    return render(request, 'editais/form.html', {'form': form, 'edital': edital})


@crre_required
def criar(request):
    return _salvar_edital(request)


@crre_required
def editar(request, pk):
    return _salvar_edital(request, get_object_or_404(Edital, pk=pk))


@crre_required
def deletar(request, pk):
    edital = get_object_or_404(Edital, pk=pk)
    if request.method == 'POST':
        titulo = edital.titulo
        edital.delete()
        messages.success(request, f'"{titulo}" foi removido da lista.')
        return redirect('editais:lista')
    return render(request, 'editais/confirmar_exclusao.html', {
        'objeto': edital,
        'nome': edital.titulo,
        'tipo': 'edital',
        'aviso': 'O robô pode trazer este edital de novo na próxima varredura. '
                 'Se a ideia é não olhar mais para ele, marque como Descartado.',
        'voltar': reverse('editais:lista'),
    })


# ────────────────────────────── Fontes ──────────────────────────────
@crre_required
def fontes(request):
    """Saúde do robô: o que cada fonte trouxe da última vez e o que quebrou."""
    todas = FonteEdital.objects.annotate(total_editais=Count('editais'))
    return render(request, 'editais/fontes.html', {
        'fontes': todas,
        'ativas': sum(1 for f in todas if f.ativo),
        'com_erro': sum(1 for f in todas if f.ativo and f.ultimo_erro),
    })


@crre_required
def fonte_form(request, pk=None):
    fonte = get_object_or_404(FonteEdital, pk=pk) if pk else None
    form = FonteEditalForm(request.POST or None, instance=fonte)
    if request.method == 'POST' and form.is_valid():
        salva = form.save()
        messages.success(request, f'Fonte "{salva.nome}" salva.')
        return redirect('editais:fontes')
    return render(request, 'editais/fonte_form.html', {'form': form, 'fonte': fonte})


@crre_required
def fonte_deletar(request, pk):
    fonte = get_object_or_404(FonteEdital, pk=pk)
    if request.method == 'POST':
        nome = fonte.nome
        fonte.delete()      # os editais ficam: a fonte vira nula (SET_NULL)
        messages.success(request, f'Fonte "{nome}" removida. Os editais já coletados continuam na lista.')
        return redirect('editais:fontes')
    return render(request, 'editais/confirmar_exclusao.html', {
        'objeto': fonte,
        'nome': fonte.nome,
        'tipo': 'fonte',
        'aviso': 'Os editais já coletados continuam na lista, apenas sem a fonte de origem. '
                 'Para só parar de varrer, desative a fonte em vez de apagar.',
        'voltar': reverse('editais:fontes'),
    })


# ────────────────────────────── Palavras-chave ──────────────────────────────
@crre_required
def palavras(request):
    """Onde o CR ensina o robô. Uma tela só: lista + formulário.

    Cadastro/edição vêm no mesmo POST (com `editar=<pk>` quando é edição) e a
    exclusão vem por `excluir=<pk>`.
    """
    pk_edicao = request.POST.get('editar') or request.GET.get('editar') or ''
    em_edicao = (PalavraChave.objects.filter(pk=pk_edicao).first()
                 if str(pk_edicao).isdigit() else None)

    if request.method == 'POST' and request.POST.get('excluir'):
        alvo = get_object_or_404(PalavraChave, pk=request.POST['excluir'])
        termo = alvo.termo
        alvo.delete()
        messages.success(request, f'"{termo}" saiu do dicionário do robô.')
        return redirect('editais:palavras')

    form = PalavraChaveForm(request.POST or None, instance=em_edicao)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Palavra-chave salva. Vale na próxima varredura.')
        return redirect('editais:palavras')

    todas = list(PalavraChave.objects.all())
    return render(request, 'editais/palavras.html', {
        'form': form,
        'em_edicao': em_edicao,
        'palavras': todas,
        'positivas': [p for p in todas if p.peso > 0],
        'negativas': [p for p in todas if p.peso < 0],
    })


# ────────────────────────────── Consultas de busca ──────────────────────────
@crre_required
def consultas(request):
    """As perguntas que o robô faz à web.

    Esta é a tela que faz a varredura ser do CR e não do programador: ler
    fontes cadastradas só encontra edital onde alguém já sabia procurar, e o
    projeto não sabia. Quem entende do que o PCF precisa é quem está aqui.

    Mesmo desenho da tela de palavras-chave: lista + formulário no mesmo POST
    (`editar=<pk>` para edição, `excluir=<pk>` para apagar).
    """
    pk_edicao = request.POST.get('editar') or request.GET.get('editar') or ''
    em_edicao = (ConsultaBusca.objects.filter(pk=pk_edicao).first()
                 if str(pk_edicao).isdigit() else None)

    if request.method == 'POST' and request.POST.get('excluir'):
        alvo = get_object_or_404(ConsultaBusca, pk=request.POST['excluir'])
        termo = alvo.termo
        alvo.delete()
        messages.success(request, f'O robô parou de perguntar "{termo}".')
        return redirect('editais:consultas')

    form = ConsultaBuscaForm(request.POST or None, instance=em_edicao)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Consulta salva. Vale na próxima varredura.')
        return redirect('editais:consultas')

    todas = list(ConsultaBusca.objects.all())
    return render(request, 'editais/consultas.html', {
        'form': form,
        'em_edicao': em_edicao,
        'consultas': todas,
        'ativas': [c for c in todas if c.ativo],
        'com_erro': [c for c in todas if c.ultimo_erro],
    })
