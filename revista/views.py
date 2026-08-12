"""Telas da revistinha do doador (área CR/RE).

Tudo aqui exige CR/RE, menos `publica`: essa é a página que o doador abre pelo
link, sem conta no sistema.
"""
from functools import wraps
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.text import slugify

from .forms import RevistaForm, SecaoRevistaFormSet
from .models import Revista
from .servicos import financeiro_do_periodo, montar_secoes, numeros_do_periodo

AREAS_CRRE = {'CR/RE', 'TRIADE'}


def crre_required(view):
    @wraps(view)
    @login_required(login_url='/login/')
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_CRRE):
            raise PermissionDenied('Esta área é do CR/RE.')
        return view(request, *args, **kwargs)
    return wrapper


def _contexto_leitura(revista):
    """O que toda visualização da revista precisa — tela interna, PDF, e-mail e
    página pública leem exatamente o mesmo conteúdo."""
    contexto = {
        'revista': revista,
        'secoes': revista.secoes_incluidas.select_related('atividade', 'sabado'),
        'numeros': None,
        'financeiro': None,
    }
    if revista.mostrar_numeros:
        contexto['numeros'] = numeros_do_periodo(revista.periodo_inicio, revista.periodo_fim)
    if revista.mostrar_financeiro:
        contexto['financeiro'] = financeiro_do_periodo(
            revista.periodo_inicio, revista.periodo_fim)
    return contexto


# ─────────────────────────── Edições ───────────────────────────
@crre_required
def lista(request):
    status = request.GET.get('status') or ''

    revistas = Revista.objects.annotate(
        total_secoes=Count('secoes', filter=Q(secoes__incluir=True)),
    )
    if status in ('RASCUNHO', 'PUBLICADA'):
        revistas = revistas.filter(status=status)

    todas = Revista.objects.all()
    return render(request, 'revista/lista.html', {
        'revistas': revistas,
        'status_selecionado': status,
        'total': todas.count(),
        'total_rascunho': todas.filter(status='RASCUNHO').count(),
        'total_publicada': todas.filter(status='PUBLICADA').count(),
    })


@crre_required
def criar(request):
    form = RevistaForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        revista = form.save(commit=False)
        revista.criado_por = request.user
        revista.save()
        # Já entrega a edição com os destaques puxados do semanário: o CR abre
        # a tela de montagem para reescrever, não para digitar do zero.
        criadas = montar_secoes(revista)
        messages.success(
            request,
            f'Revista criada com {criadas} seção(ões) montada(s) a partir do semanário.'
            if criadas else
            'Revista criada. Não achei atividades com descrição nesse período — '
            'confira as datas ou escreva as seções à mão.'
        )
        return redirect('revista:montar', pk=revista.pk)
    return render(request, 'revista/form.html', {'form': form, 'revista': None})


@crre_required
def editar(request, pk):
    revista = get_object_or_404(Revista, pk=pk)
    form = RevistaForm(request.POST or None, instance=revista)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Dados da revista salvos.')
        return redirect('revista:montar', pk=revista.pk)
    return render(request, 'revista/form.html', {'form': form, 'revista': revista})


@crre_required
def montar(request, pk):
    revista = get_object_or_404(Revista, pk=pk)
    queryset = revista.secoes.select_related('atividade', 'sabado')

    if request.method == 'POST' and request.POST.get('acao') == 'remontar':
        # "Substituir" joga fora o texto reescrito pelo CR, então é uma escolha
        # explícita na tela, nunca o padrão.
        substituir = request.POST.get('substituir') == '1'
        criadas = montar_secoes(revista, substituir=substituir)
        if substituir:
            messages.success(request, f'Revista remontada do zero: {criadas} seção(ões).')
        elif criadas:
            messages.success(request, f'{criadas} seção(ões) nova(s) trazida(s) do semanário.')
        else:
            messages.info(request, 'Nenhuma atividade nova para trazer nesse período.')
        return redirect('revista:montar', pk=revista.pk)

    if request.method == 'POST':
        formset = SecaoRevistaFormSet(request.POST, request.FILES, queryset=queryset)
        if formset.is_valid():
            # Anota o descarte ANTES de salvar: depois do save() as seções
            # apagadas já não existem para consultar. Sem esse registro, o
            # próximo "remontar do semanário" traria de volta exatamente as
            # atividades que o CR acabou de tirar.
            descartadas = [
                form.instance.atividade_id
                for form in formset.deleted_forms
                if form.instance.pk and form.instance.atividade_id
            ]
            formset.save()
            if descartadas:
                guardadas = list(revista.atividades_descartadas or [])
                revista.atividades_descartadas = sorted(set(guardadas) | set(descartadas))
                revista.save(update_fields=['atividades_descartadas'])
            messages.success(request, 'Seções salvas.')
            return redirect('revista:montar', pk=revista.pk)
        messages.error(request, 'Confira os campos destacados: as seções não foram salvas.')
    else:
        formset = SecaoRevistaFormSet(queryset=queryset)

    return render(request, 'revista/montar.html', {
        'revista': revista,
        'formset': formset,
        'numeros': numeros_do_periodo(revista.periodo_inicio, revista.periodo_fim),
    })


@crre_required
def ver(request, pk):
    revista = get_object_or_404(Revista, pk=pk)
    return render(request, 'revista/ver.html', _contexto_leitura(revista))


@crre_required
def email_html(request, pk):
    revista = get_object_or_404(Revista, pk=pk)
    return render(request, 'revista/email.html', _contexto_leitura(revista))


@crre_required
def pdf(request, pk):
    revista = get_object_or_404(Revista, pk=pk)
    contexto = _contexto_leitura(revista)

    from xhtml2pdf import pisa

    html = render_to_string('revista/pdf.html', contexto)
    buffer = BytesIO()
    resultado = pisa.CreatePDF(html, dest=buffer, encoding='utf-8')
    if resultado.err:
        # Não devolva um PDF corrompido em silêncio.
        messages.error(request, 'Não consegui gerar o PDF. Use "Imprimir" na tela da revista.')
        return redirect('revista:ver', pk=revista.pk)

    nome_arquivo = slugify(revista.titulo) or f'revista-{revista.pk}'
    resposta = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    resposta['Content-Disposition'] = f'attachment; filename="{nome_arquivo}.pdf"'
    return resposta


@crre_required
def publicar(request, pk):
    revista = get_object_or_404(Revista, pk=pk)
    if request.method != 'POST':
        return redirect('revista:ver', pk=revista.pk)

    acao = request.POST.get('acao')
    if acao == 'publicar':
        revista.status = 'PUBLICADA'
        revista.link_publico_ativo = True
        messages.success(request, 'Revista publicada. O link do doador já abre.')
    elif acao == 'revogar':
        # Revogar sem despublicar: o link morre na hora, o conteúdo continua
        # publicado internamente.
        revista.link_publico_ativo = False
        messages.success(request, 'Link público revogado. Quem tinha o endereço não abre mais.')
    else:
        revista.status = 'RASCUNHO'
        revista.link_publico_ativo = False
        messages.success(request, 'Revista voltou para rascunho e o link foi desligado.')

    revista.save()
    return redirect('revista:ver', pk=revista.pk)


@crre_required
def deletar(request, pk):
    revista = get_object_or_404(Revista, pk=pk)
    if request.method == 'POST':
        titulo = revista.titulo
        revista.delete()
        messages.success(request, f'A revista "{titulo}" foi apagada.')
        return redirect('revista:lista')
    return render(request, 'revista/confirmar_exclusao.html', {'revista': revista})


# ─────────────────────────── Página do doador ───────────────────────────
def publica(request, token):
    """Página aberta pelo link, sem login. Não tem sidebar nem navbar: quem
    abre não é do projeto."""
    revista = get_object_or_404(Revista, token=token)

    # 404 em vez de 403: para quem tem o link revogado, a página simplesmente
    # não existe — não confirmamos que aquele token um dia foi válido.
    if not revista.link_publico_valido or revista.status != 'PUBLICADA':
        raise Http404('Revista não disponível.')

    resposta = render(request, 'revista/publica.html', _contexto_leitura(revista))
    # Tem foto de criança nesta página: não pode ser indexada nem arquivada.
    resposta['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    # A promessa desta tela é "posso revogar a qualquer momento". Sem isto, um
    # cache no caminho (ou o próprio navegador do doador) continuaria servindo
    # a edição depois de revogada, e a revogação viraria só um gesto.
    resposta['Cache-Control'] = 'private, no-store, max-age=0'
    return resposta
