# ronda/views.py
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from functools import wraps
from django.utils import timezone

from .models import (
    LocalRonda, ConfiguracaoRondaSabado, HorarioRonda,
    EscalaRonda, ScoreRonda, AREAS_ISENTAS_RONDA,
)
from .forms import (
    LocalRondaForm, ConfiguracaoRondaForm, HorarioRondaFormSet, ScoreRondaForm,
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
        return redirect('ronda:configuracao_detalhe', pk=cfg.pk)
    return render(request, 'form_configuracao.html', {'form': form, 'formset': formset})


# ── Detalhe + ações ──────────────────────────────────────────────────────────

@ronda_required
def configuracao_detalhe(request, pk):
    cfg = get_object_or_404(ConfiguracaoRondaSabado, pk=pk)
    locais = LocalRonda.objects.filter(ativo=True)
    horarios = cfg.horarios.prefetch_related('escalas__voluntario', 'escalas__local').all()

    # Monta grade: {horario.pk: {local.pk: [escalas]}}
    grade = {}
    for h in horarios:
        grade[h.pk] = {l.pk: [] for l in locais}
        for e in h.escalas.all():
            grade[h.pk][e.local_id].append(e)

    from voluntario.models import Voluntario
    elegiveis = (
        Voluntario.objects.filter(data_saida__isnull=True)
        .exclude(area__in=AREAS_ISENTAS_RONDA)
        .order_by('first_name', 'last_name')
    )
    ano_atual = timezone.now().year
    scores = {
        s.voluntario_id: s.pontos
        for s in ScoreRonda.objects.filter(voluntario__in=elegiveis, ano=ano_atual)
    }

    return render(request, 'detalhe_configuracao.html', {
        'cfg': cfg,
        'locais': locais,
        'horarios': horarios,
        'grade': grade,
        'elegiveis': elegiveis,
        'scores': scores,
    })


@ronda_required
def configuracao_sortear(request, pk):
    cfg = get_object_or_404(ConfiguracaoRondaSabado, pk=pk)
    if request.method == 'POST':
        if cfg.status not in ('PENDENTE_SORTEIO', 'REPROVADA'):
            messages.error(request, 'Só é possível sortear configurações pendentes ou reprovadas.')
            return redirect('ronda:configuracao_detalhe', pk=pk)
        if not cfg.horarios.exists():
            messages.error(request, 'Adicione ao menos um horário antes de sortear.')
            return redirect('ronda:configuracao_detalhe', pk=pk)
        from .sorteio import executar_sorteio
        executar_sorteio(cfg)
        messages.success(request, 'Sorteio realizado com sucesso!')
    return redirect('ronda:configuracao_detalhe', pk=pk)


@ronda_required
def configuracao_aprovar(request, pk):
    cfg = get_object_or_404(ConfiguracaoRondaSabado, pk=pk)
    if request.method == 'POST':
        if cfg.status != 'SORTEADA':
            messages.error(request, 'Só é possível aprovar rondas sorteadas.')
            return redirect('ronda:configuracao_detalhe', pk=pk)
        ano_atual = timezone.now().year
        for escala in EscalaRonda.objects.filter(horario__configuracao=cfg):
            ScoreRonda.incrementar(escala.voluntario, ano_atual)
        cfg.status = 'APROVADA'
        cfg.aprovado_por = request.user
        cfg.aprovado_em = timezone.now()
        cfg.save(update_fields=['status', 'aprovado_por', 'aprovado_em'])
        messages.success(request, 'Ronda aprovada e scores atualizados!')
    return redirect('ronda:configuracao_detalhe', pk=pk)


@ronda_required
def configuracao_reprovar(request, pk):
    cfg = get_object_or_404(ConfiguracaoRondaSabado, pk=pk)
    if request.method == 'POST':
        if cfg.status != 'SORTEADA':
            messages.error(request, 'Só é possível reprovar rondas sorteadas.')
            return redirect('ronda:configuracao_detalhe', pk=pk)
        observacao = request.POST.get('observacao', '').strip()
        if not observacao:
            messages.error(request, 'Informe o motivo da reprovação.')
            return redirect('ronda:configuracao_detalhe', pk=pk)
        cfg.status = 'REPROVADA'
        cfg.observacao = observacao
        cfg.save(update_fields=['status', 'observacao'])
        messages.success(request, 'Ronda reprovada. Você pode re-sortear.')
    return redirect('ronda:configuracao_detalhe', pk=pk)


@ronda_required
def escala_swap(request, pk):
    escala = get_object_or_404(EscalaRonda, pk=pk)
    if request.method != 'POST':
        return redirect('ronda:configuracao_detalhe', pk=escala.horario.configuracao_id)

    cfg = escala.horario.configuracao
    if cfg.status not in ('SORTEADA', 'PENDENTE_SORTEIO'):
        messages.error(request, 'Só é possível trocar voluntários antes da aprovação.')
        return redirect('ronda:configuracao_detalhe', pk=cfg.pk)

    from voluntario.models import Voluntario
    novo_pk = request.POST.get('voluntario_novo_pk')
    try:
        novo_vol = Voluntario.objects.get(pk=novo_pk, data_saida__isnull=True)
    except Voluntario.DoesNotExist:
        messages.error(request, 'Voluntário não encontrado ou inativo.')
        return redirect('ronda:configuracao_detalhe', pk=cfg.pk)

    if novo_vol.area in AREAS_ISENTAS_RONDA:
        messages.error(request, f'Voluntários da área {novo_vol.area} não podem fazer rondas.')
        return redirect('ronda:configuracao_detalhe', pk=cfg.pk)

    ja_no_horario = EscalaRonda.objects.filter(
        horario=escala.horario, voluntario=novo_vol
    ).exclude(pk=escala.pk).exists()
    if ja_no_horario:
        messages.error(request, 'Este voluntário já está escalado neste horário.')
        return redirect('ronda:configuracao_detalhe', pk=cfg.pk)

    escala.voluntario_original = escala.voluntario_original or escala.voluntario
    escala.voluntario = novo_vol
    escala.is_substituto = True
    escala.save(update_fields=['voluntario', 'voluntario_original', 'is_substituto'])
    messages.success(request, f'Substituição realizada: {novo_vol.get_full_name()}')
    return redirect('ronda:configuracao_detalhe', pk=cfg.pk)


# ── Ranking ──────────────────────────────────────────────────────────────────

@ronda_required
def ranking(request):
    from voluntario.models import Voluntario, LISTA_AREAS
    ano_atual = timezone.now().year
    area_filtro = request.GET.get('area', '')

    vols_qs = (
        Voluntario.objects.filter(data_saida__isnull=True)
        .exclude(area__in=AREAS_ISENTAS_RONDA)
        .order_by('first_name', 'last_name')
    )
    if area_filtro:
        vols_qs = vols_qs.filter(area=area_filtro)

    scores_map = {
        s.voluntario_id: s
        for s in ScoreRonda.objects.filter(voluntario__in=vols_qs, ano=ano_atual)
    }

    ultima_map = {}
    for e in (
        EscalaRonda.objects
        .filter(horario__configuracao__status='APROVADA', voluntario__in=vols_qs)
        .select_related('horario__configuracao__sabado')
        .order_by('horario__configuracao__sabado__data')
    ):
        ultima_map[e.voluntario_id] = e.horario.configuracao.sabado.data

    hoje = timezone.now().date()
    voluntarios = []
    for v in vols_qs:
        score_obj = scores_map.get(v.pk)
        pontos = score_obj.pontos if score_obj else 0
        ultima = ultima_map.get(v.pk)
        if ultima is None:
            badge = 'nunca'
        elif (hoje - ultima).days > 45:
            badge = 'antigo'
        else:
            badge = 'ok'
        voluntarios.append({'vol': v, 'pontos': pontos, 'ultima': ultima, 'badge': badge})

    voluntarios.sort(key=lambda x: x['pontos'])

    areas_elegiveis = [(k, v) for k, v in LISTA_AREAS if k not in AREAS_ISENTAS_RONDA]

    return render(request, 'ranking_ronda.html', {
        'voluntarios': voluntarios,
        'area_filtro': area_filtro,
        'areas_elegiveis': areas_elegiveis,
        'ano': ano_atual,
    })


@ronda_required
def score_editar(request, pk):
    score = get_object_or_404(ScoreRonda, pk=pk)
    form = ScoreRondaForm(request.POST or None, instance=score)
    if form.is_valid():
        form.save()
        messages.success(request, f'Score de {score.voluntario.get_full_name()} atualizado para {score.pontos} pt(s).')
        return redirect('ronda:ranking')
    return render(request, 'form_score.html', {'form': form, 'score': score})


# ── Área pública ─────────────────────────────────────────────────────────────

@login_required
def ronda_publica(request):
    configuracoes = (
        ConfiguracaoRondaSabado.objects
        .filter(status='APROVADA')
        .prefetch_related('horarios__escalas__voluntario', 'horarios__escalas__local')
        .select_related('sabado')
        .order_by('-sabado__data')
    )
    locais = LocalRonda.objects.filter(ativo=True)

    grades = {}
    for cfg in configuracoes:
        grades[cfg.pk] = {}
        for h in cfg.horarios.all():
            grades[cfg.pk][h.pk] = {l.pk: [] for l in locais}
            for e in h.escalas.all():
                grades[cfg.pk][h.pk][e.local_id].append(e)

    return render(request, 'ronda_publica.html', {
        'configuracoes': configuracoes,
        'locais': locais,
        'grades': grades,
    })
