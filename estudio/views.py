"""Telas do estúdio.

Permissão: qualquer voluntário logado cria e edita documento — Ata é do
projeto inteiro, não de uma área. A exceção é documento ligado a uma REVISTA:
esse segue o mesmo portão da revista (CR/RE, Tríade, superusuário), porque
mexer nele é mexer no que vai para o doador.

Salvar é uma chamada só, com a página inteira em JSON. Salvar elemento por
elemento pareceria mais econômico, mas arrastar uma caixa mexe em posição,
tamanho e camada de uma vez — e meia gravação deixaria a página torta.
"""
import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AssetForm, DocumentoForm
from .models import (ESTILOS_ACEITOS, TIPOS_DE_DOCUMENTO, Asset, Documento,
                     Elemento, Pagina)
from .presets import PRESETS, aplicar

AREAS_DA_REVISTA = {'CR/RE', 'TRIADE'}

# Trava de sanidade nas coordenadas. O editor manda número, mas requisição é
# requisição: sem limite, um valor absurdo viraria página de 2 milhões de px e
# derrubaria o navegador de quem abrisse depois.
LIMITE_COORDENADA = 20000
LIMITE_TAMANHO = 20000


def _pode_mexer(usuario, documento):
    """Documento de revista tem o portão da revista; o resto é de todos."""
    if documento.revista_id is None:
        return True
    return bool(usuario.is_superuser
                or getattr(usuario, 'area', None) in AREAS_DA_REVISTA)


def documento_para_edicao(view):
    @wraps(view)
    @login_required(login_url='/login/')
    def wrapper(request, pk, *args, **kwargs):
        documento = get_object_or_404(
            Documento.objects.select_related('revista'), pk=pk)
        if not _pode_mexer(request.user, documento):
            raise PermissionDenied('Este documento é da revista — só CR/RE e Tríade editam.')
        return view(request, documento, *args, **kwargs)
    return wrapper


# ────────────────────────────── Geral ──────────────────────────────
@login_required(login_url='/login/')
def lista(request):
    """A área Geral: todo documento do estúdio. Contexto: documentos, tipo, tipos."""
    tipo = (request.GET.get('tipo') or '').strip()
    documentos = Documento.objects.select_related('revista', 'criado_por')
    if tipo in dict(TIPOS_DE_DOCUMENTO):
        documentos = documentos.filter(tipo=tipo)
    return render(request, 'estudio/lista.html', {
        'documentos': documentos,
        'tipo': tipo,
        'tipos': TIPOS_DE_DOCUMENTO,
    })


@login_required(login_url='/login/')
def criar(request):
    """Cria o documento já com a primeira página. Contexto: form, presets."""
    if request.method == 'POST':
        form = DocumentoForm(request.POST)
        if form.is_valid():
            documento = form.save(commit=False)
            documento.criado_por = request.user
            documento.save()
            # Documento sem página abre num editor vazio que não explica o que
            # fazer. Nasce com uma.
            pagina = Pagina.objects.create(documento=documento, ordem=0)
            preset = request.POST.get('preset') or 'branca'
            aplicar(pagina, preset, titulo=documento.titulo)
            return redirect('estudio:editor', pk=documento.pk)
    else:
        form = DocumentoForm()
    return render(request, 'estudio/form.html', {
        'form': form,
        'presets': [(nome, rotulo) for nome, (rotulo, _) in PRESETS.items()],
    })


@documento_para_edicao
def apagar(request, documento):
    if request.method == 'POST':
        documento.delete()
        messages.success(request, 'Documento apagado.')
        return redirect('estudio:lista')
    return render(request, 'estudio/confirmar_exclusao.html', {'documento': documento})


# ────────────────────────────── Editor ──────────────────────────────
def _estado_do_editor(documento):
    """Tudo que o editor precisa, num objeto só.

    Vai para a página por `json_script`, que é a forma do Django de entregar
    dado a JavaScript sem virar HTML — ele escapa o que precisa e o JS lê com
    JSON.parse. Montar isso em atributos `data-` daria o mesmo resultado com
    dez lugares para escapar errado.
    """
    assets = {
        str(a.pk): {'id': a.pk, 'nome': a.nome, 'url': a.arquivo.url,
                    'categoria': a.categoria, 'apelido': a.apelido or ''}
        for a in Asset.objects.all()
    }
    paginas = []
    for pagina in documento.paginas.prefetch_related('elementos'):
        paginas.append({
            'id': pagina.pk,
            'ordem': pagina.ordem,
            'cor_de_fundo': pagina.css_de_fundo,
            'preset': pagina.preset,
            'elementos': [
                {'id': el.pk, 'tipo': el.tipo, 'x': el.x, 'y': el.y,
                 'largura': el.largura, 'altura': el.altura,
                 'rotacao': el.rotacao, 'z': el.z, 'texto': el.texto,
                 'imagem': el.imagem_id, 'estilo': el.estilo or {},
                 'travado': el.travado}
                for el in pagina.elementos.all()
            ],
        })
    return {
        'largura': documento.largura,
        'altura': documento.altura,
        'assets': assets,
        'paginas': paginas,
    }


@documento_para_edicao
def editor(request, documento):
    """A tela de edição. Contexto: documento, paginas, assets, presets, estado."""
    paginas = documento.paginas.prefetch_related('elementos__imagem')
    return render(request, 'estudio/editor.html', {
        'documento': documento,
        'paginas': paginas,
        'assets': Asset.objects.all(),
        'form_asset': AssetForm(),
        'presets': [(nome, rotulo) for nome, (rotulo, _) in PRESETS.items()],
        'estado': _estado_do_editor(documento),
        'limite_coordenada': LIMITE_COORDENADA,
    })


def _inteiro(valor, minimo, maximo, padrao=0):
    """Número que veio de requisição: convertido e preso na faixa.

    Vale para tudo que chega do editor. `int(valor)` solto estouraria em
    ValueError com string, e valor absurdo viraria página impossível de abrir.
    """
    try:
        numero = int(round(float(valor)))
    except (TypeError, ValueError):
        return padrao
    return max(minimo, min(maximo, numero))


@documento_para_edicao
@require_POST
def salvar_pagina(request, documento, pagina_pk):
    """Troca os elementos da página pelos que vieram no JSON.

    Substituir em bloco, e não casar elemento por elemento: o editor é a fonte
    da verdade da página aberta, e diff incremental abriria a porta para
    estado fantasma quando duas abas salvam.
    """
    pagina = get_object_or_404(Pagina, pk=pagina_pk, documento=documento)

    try:
        dados = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'erro': 'JSON inválido.'}, status=400)

    elementos = dados.get('elementos')
    if not isinstance(elementos, list):
        return JsonResponse({'ok': False, 'erro': 'Falta a lista de elementos.'}, status=400)

    cor = str(dados.get('cor_de_fundo') or pagina.cor_de_fundo)[:20]

    novos = []
    for indice, bruto in enumerate(elementos):
        if not isinstance(bruto, dict):
            continue
        tipo = bruto.get('tipo')
        if tipo not in {'TEXTO', 'IMAGEM', 'FORMA'}:
            continue

        asset = None
        if tipo == 'IMAGEM':
            asset = Asset.objects.filter(pk=bruto.get('imagem')).first()
            if asset is None:
                continue      # imagem sem arquivo não é elemento, é buraco

        estilo = bruto.get('estilo')
        if not isinstance(estilo, dict):
            estilo = {}

        elemento = Elemento(
            pagina=pagina,
            tipo=tipo,
            x=_inteiro(bruto.get('x'), -LIMITE_COORDENADA, LIMITE_COORDENADA),
            y=_inteiro(bruto.get('y'), -LIMITE_COORDENADA, LIMITE_COORDENADA),
            largura=_inteiro(bruto.get('largura'), 1, LIMITE_TAMANHO, padrao=100),
            altura=_inteiro(bruto.get('altura'), 1, LIMITE_TAMANHO, padrao=40),
            rotacao=_inteiro(bruto.get('rotacao'), -180, 180),
            z=_inteiro(bruto.get('z'), -999, 999, padrao=indice),
            texto=str(bruto.get('texto') or '')[:20000],
            imagem=asset,
            estilo=estilo,
            travado=bool(bruto.get('travado')),
        )
        try:
            elemento.clean()          # filtra chaves de estilo desconhecidas
        except ValidationError:
            continue
        novos.append(elemento)

    # Só depois de montar tudo: se a validação derrubasse metade, apagar antes
    # deixaria a página pela metade e sem volta.
    pagina.elementos.all().delete()
    Elemento.objects.bulk_create(novos)
    pagina.cor_de_fundo = cor
    pagina.save(update_fields=['cor_de_fundo'])

    return JsonResponse({'ok': True, 'salvos': len(novos)})


@documento_para_edicao
@require_POST
def pagina_nova(request, documento):
    ultima = documento.paginas.aggregate(m=Max('ordem'))['m']
    pagina = Pagina.objects.create(
        documento=documento, ordem=0 if ultima is None else ultima + 1)
    preset = request.POST.get('preset') or 'branca'
    numero = pagina.ordem + 1
    aplicar(pagina, preset, titulo=documento.titulo, numero=numero,
            sala=request.POST.get('sala') or 'VIOLETA')
    return redirect('estudio:editor', pk=documento.pk)


@documento_para_edicao
@require_POST
def pagina_apagar(request, documento, pagina_pk):
    pagina = get_object_or_404(Pagina, pk=pagina_pk, documento=documento)
    if documento.paginas.count() == 1:
        messages.warning(request, 'O documento precisa de pelo menos uma página.')
        return redirect('estudio:editor', pk=documento.pk)
    pagina.delete()
    # Renumera para não sobrar buraco na ordem — o `ordem` vira o número
    # impresso da página no preset.
    for indice, restante in enumerate(documento.paginas.all()):
        if restante.ordem != indice:
            restante.ordem = indice
            restante.save(update_fields=['ordem'])
    return redirect('estudio:editor', pk=documento.pk)


@documento_para_edicao
@require_POST
def pagina_mover(request, documento, pagina_pk):
    """Sobe ou desce a página uma posição, trocando com a vizinha."""
    pagina = get_object_or_404(Pagina, pk=pagina_pk, documento=documento)
    direcao = request.POST.get('direcao')
    if direcao == 'cima':
        vizinha = documento.paginas.filter(ordem__lt=pagina.ordem).last()
    elif direcao == 'baixo':
        vizinha = documento.paginas.filter(ordem__gt=pagina.ordem).first()
    else:
        vizinha = None

    if vizinha:
        pagina.ordem, vizinha.ordem = vizinha.ordem, pagina.ordem
        pagina.save(update_fields=['ordem'])
        vizinha.save(update_fields=['ordem'])
    return redirect('estudio:editor', pk=documento.pk)


# ────────────────────────────── Assets ──────────────────────────────
@login_required(login_url='/login/')
def assets(request):
    """Lista o acervo de imagens em JSON, para o seletor do editor."""
    return JsonResponse({'assets': [
        {'id': a.pk, 'nome': a.nome, 'categoria': a.categoria,
         'apelido': a.apelido or '', 'url': a.arquivo.url}
        for a in Asset.objects.all()
    ]})


@login_required(login_url='/login/')
@require_POST
def asset_novo(request):
    form = AssetForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({'ok': False, 'erros': form.errors}, status=400)
    asset = form.save(commit=False)
    asset.enviado_por = request.user
    asset.save()
    return JsonResponse({'ok': True, 'asset': {
        'id': asset.pk, 'nome': asset.nome, 'categoria': asset.categoria,
        'apelido': asset.apelido or '', 'url': asset.arquivo.url,
    }})


# ────────────────────────────── Leitura ──────────────────────────────
@login_required(login_url='/login/')
def ver(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    return render(request, 'estudio/ver.html', {
        'documento': documento,
        'paginas': documento.paginas.prefetch_related('elementos__imagem'),
        'para_impressao': False,
    })


@login_required(login_url='/login/')
def imprimir(request, pk):
    """Mesmo desenho, sem nada de interface — é isto que vira PDF no navegador."""
    documento = get_object_or_404(Documento, pk=pk)
    return render(request, 'estudio/imprimir.html', {
        'documento': documento,
        'paginas': documento.paginas.prefetch_related('elementos__imagem'),
        'para_impressao': True,
    })


# ────────────────────── Ponte com a revistinha ──────────────────────
@login_required(login_url='/login/')
@require_POST
def gerar_da_revista(request, revista_pk):
    """Monta um documento com as páginas da revista já preenchidas.

    O conteúdo continua nascendo dos semanários: as seções da revista viram as
    páginas de salinha, com o texto que o CR já revisou. Depois disso o
    documento é livre — mexer aqui não volta para a revista, e é de propósito:
    o layout é decisão de quem desenha, não do semanário.
    """
    from revista.models import Revista

    revista = get_object_or_404(Revista, pk=revista_pk)
    if not (request.user.is_superuser
            or getattr(request.user, 'area', None) in AREAS_DA_REVISTA):
        raise PermissionDenied('A revistinha é do CR/RE.')

    if getattr(revista, 'documento', None) is not None:
        messages.info(request, 'Esta revista já tem layout no estúdio.')
        return redirect('estudio:editor', pk=revista.documento.pk)

    documento = Documento.objects.create(
        titulo=revista.titulo, tipo='REVISTA', revista=revista,
        criado_por=request.user)

    ordem = 0
    capa = Pagina.objects.create(documento=documento, ordem=ordem)
    aplicar(capa, 'capa', titulo=revista.titulo,
            edicao=revista.subtitulo or '')
    ordem += 1

    secoes = list(revista.secoes_incluidas)

    sumario = Pagina.objects.create(documento=documento, ordem=ordem)
    aplicar(sumario, 'sumario', itens=[
        (secao.titulo, str(indice + 1)) for indice, secao in enumerate(secoes[:8])
    ])
    ordem += 1

    for indice, secao in enumerate(secoes):
        pagina = Pagina.objects.create(documento=documento, ordem=ordem)
        aplicar(pagina, 'salinha', sala=(secao.sala or 'VIOLETA'),
                texto=secao.texto, foto_a_esquerda=bool(indice % 2),
                numero=ordem - 1)
        ordem += 1

    fim = Pagina.objects.create(documento=documento, ordem=ordem)
    aplicar(fim, 'contracapa')

    messages.success(
        request,
        f'Layout criado com {documento.total_paginas} página(s). '
        'Suba as artes do Canva no acervo para as faixas e os nomes das salas aparecerem.')
    return redirect('estudio:editor', pk=documento.pk)
