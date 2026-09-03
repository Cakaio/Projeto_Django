"""Telas do acervo.

Permissão em duas camadas, e a diferença entre elas é o ponto:

  LER   — qualquer voluntário logado. Decisão da liderança, tomada sabendo que
          a coleção de postulações inclui documento de quem não foi eleito.
  MEXER — Tríade e superusuário. Quem conduz postulação é quem sabe o que pode
          entrar no acervo; upload aberto a todos num acervo aberto a todos
          seria pasta pública dentro do sistema.

Os templates são escritos à parte (`acervo/lista.html`, `colecao.html`,
`form.html`, `confirmar_exclusao.html`).
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ColecaoForm, DocumentoForm
from .models import RESULTADO_POSTULACAO, Colecao, Documento

AREAS_DE_ESCRITA = {'TRIADE'}


def pode_mexer(user):
    return bool(user.is_superuser or getattr(user, 'area', None) in AREAS_DE_ESCRITA)


def escrita_required(view):
    @wraps(view)
    @login_required(login_url='/login/')
    def wrapper(request, *args, **kwargs):
        if not pode_mexer(request.user):
            raise PermissionDenied('Só a Tríade cadastra no acervo.')
        return view(request, *args, **kwargs)
    return wrapper


# ────────────────────────────── Leitura ──────────────────────────────
@login_required(login_url='/login/')
def lista(request):
    """As coleções do acervo. Contexto: colecoes, pode_mexer, total."""
    colecoes = (Colecao.objects.filter(ativo=True)
                .annotate(quantos=Count('documentos')))
    return render(request, 'acervo/lista.html', {
        'colecoes': colecoes,
        'pode_mexer': pode_mexer(request.user),
        'total': sum(c.quantos for c in colecoes),
    })


@login_required(login_url='/login/')
def colecao(request, slug):
    """Os documentos de uma coleção, com busca e filtros.

    Contexto: colecao, documentos, anos, q, ano, resultado, resultados,
    pode_mexer.
    """
    obj = get_object_or_404(Colecao, slug=slug, ativo=True)

    busca = (request.GET.get('q') or '').strip()
    ano = (request.GET.get('ano') or '').strip()
    resultado = (request.GET.get('resultado') or '').strip()

    documentos = obj.documentos.select_related('pessoa', 'enviado_por')
    if busca:
        documentos = documentos.filter(
            Q(titulo__icontains=busca)
            | Q(descricao__icontains=busca)
            | Q(nome_avulso__icontains=busca)
            | Q(cargo_pretendido__icontains=busca)
            | Q(pessoa__first_name__icontains=busca)
            | Q(pessoa__last_name__icontains=busca)
        )
    # Ano vem da URL: validar antes de filtrar, porque `?ano=abc` levantaria
    # ValueError dentro do queryset e viraria erro 500.
    if ano.isdigit():
        documentos = documentos.filter(ano=int(ano))
    if resultado in dict(RESULTADO_POSTULACAO):
        documentos = documentos.filter(resultado=resultado)

    return render(request, 'acervo/colecao.html', {
        'colecao': obj,
        'documentos': documentos,
        'anos': (obj.documentos.values_list('ano', flat=True)
                 .distinct().order_by('-ano')),
        'q': busca,
        'ano': ano,
        'resultado': resultado,
        'resultados': RESULTADO_POSTULACAO,
        'pode_mexer': pode_mexer(request.user),
    })


# ────────────────────────────── Escrita ──────────────────────────────
@escrita_required
def documento_form(request, pk=None):
    """Cadastra ou edita um documento. Contexto: form, documento, titulo."""
    documento = get_object_or_404(Documento, pk=pk) if pk else None

    if request.method == 'POST':
        form = DocumentoForm(request.POST, request.FILES, instance=documento)
        if form.is_valid():
            novo = form.save(commit=False)
            if novo.enviado_por_id is None:
                novo.enviado_por = request.user
            novo.save()
            messages.success(request, 'Documento salvo no acervo.')
            return redirect('acervo:colecao', slug=novo.colecao.slug)
    else:
        form = DocumentoForm(instance=documento)

    return render(request, 'acervo/form.html', {
        'form': form,
        'documento': documento,
        'titulo': 'Editar documento' if documento else 'Novo documento',
    })


@escrita_required
def documento_deletar(request, pk):
    """Apaga um documento, com confirmação. Contexto: tipo, nome, voltar."""
    documento = get_object_or_404(Documento, pk=pk)
    slug = documento.colecao.slug

    if request.method == 'POST':
        documento.delete()
        messages.success(request, 'Documento removido do acervo.')
        return redirect('acervo:colecao', slug=slug)

    return render(request, 'acervo/confirmar_exclusao.html', {
        'tipo': 'documento',
        'nome': str(documento),
        'voltar': 'acervo:colecao',
        'voltar_slug': slug,
    })


@escrita_required
def colecao_form(request, pk=None):
    """Cria ou edita uma coleção. Contexto: form, colecao, titulo."""
    obj = get_object_or_404(Colecao, pk=pk) if pk else None

    if request.method == 'POST':
        form = ColecaoForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Coleção salva.')
            return redirect('acervo:lista')
    else:
        form = ColecaoForm(instance=obj)

    return render(request, 'acervo/form.html', {
        'form': form,
        'colecao': obj,
        'titulo': 'Editar coleção' if obj else 'Nova coleção',
    })
