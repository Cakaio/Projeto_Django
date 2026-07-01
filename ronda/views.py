# ronda/views.py
from collections import OrderedDict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from functools import wraps
from django.db.models import F
from django.utils import timezone

from .models import (
    LocalRonda, ConfiguracaoRondaSabado, HorarioRonda,
    EscalaRonda, ScoreRonda, AREAS_ISENTAS_RONDA,
)
from .forms import (
    LocalRondaForm, ConfiguracaoRondaForm, HorarioRondaFormSet, ScoreRondaForm,
)

RONDA_GESTAO = {'TRIADE'}


def _reordenar_horarios(cfg):
    """Mantém a 'ordem' coerente com a sequência cronológica dos horários."""
    for i, h in enumerate(cfg.horarios.order_by('hora_inicio', 'local__nome')):
        if h.ordem != i:
            HorarioRonda.objects.filter(pk=h.pk).update(ordem=i)


def _contar_confirmados(sabado):
    """Voluntários elegíveis (ativos, não isentos) que confirmaram presença no sábado."""
    from voluntario.models import Voluntario
    return (
        Voluntario.objects.filter(
            data_saida__isnull=True,
            disponibilidades__sabado=sabado,
            disponibilidades__vai_ao_projeto=True,
        )
        .exclude(area__in=AREAS_ISENTAS_RONDA)
        .distinct()
        .count()
    )


def _grade_evento(horarios):
    """Modo dia de evento: cada horário = um local com 2 duplas fixas."""
    grade = []
    for h in horarios:
        escalas = list(h.escalas.all())
        grade.append({
            'local': h.local,
            'dupla1': [e for e in escalas if e.dupla == 1],
            'dupla2': [e for e in escalas if e.dupla == 2],
        })
    return grade


def _mapa_ultima_ronda():
    """{voluntario_id: data da última ronda aprovada}."""
    ultima = {}
    for e in (
        EscalaRonda.objects
        .filter(horario__configuracao__status='APROVADA')
        .select_related('horario__configuracao__sabado')
        .order_by('horario__configuracao__sabado__data')
    ):
        ultima[e.voluntario_id] = e.horario.configuracao.sabado.data
    return ultima


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
    status_filtro = request.GET.get('status', '')
    qs = ConfiguracaoRondaSabado.objects.select_related('sabado', 'criado_por').all()
    if status_filtro:
        qs = qs.filter(status=status_filtro)

    todas = ConfiguracaoRondaSabado.objects.all()
    resumo = {
        'total':      todas.count(),
        'pendentes':  todas.filter(status='PENDENTE_SORTEIO').count(),
        'sorteadas':  todas.filter(status='SORTEADA').count(),
        'aprovadas':  todas.filter(status='APROVADA').count(),
        'reprovadas': todas.filter(status='REPROVADA').count(),
    }
    hoje = timezone.now().date()
    proxima = (
        ConfiguracaoRondaSabado.objects
        .filter(status='APROVADA', sabado__data__gte=hoje)
        .select_related('sabado')
        .order_by('sabado__data')
        .first()
    )
    return render(request, 'painel_ronda.html', {
        'configuracoes': qs,
        'resumo': resumo,
        'status_filtro': status_filtro,
        'proxima': proxima,
    })


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
        _reordenar_horarios(cfg)
        messages.success(request, 'Ronda criada! Agora você pode sortear.')
        return redirect('ronda:configuracao_detalhe', pk=cfg.pk)
    return render(request, 'form_configuracao.html', {
        'form': form, 'formset': formset, 'modo': 'criar',
    })


@ronda_required
def configuracao_editar(request, pk):
    cfg = get_object_or_404(ConfiguracaoRondaSabado, pk=pk)
    if cfg.status == 'APROVADA':
        messages.error(request, 'Rondas aprovadas não podem ser editadas. Exclua ou reprove antes.')
        return redirect('ronda:configuracao_detalhe', pk=pk)

    from sabado.models import Sabado
    form = ConfiguracaoRondaForm(request.POST or None, instance=cfg)
    # O sábado é a identidade da ronda — não pode ser trocado na edição.
    form.fields['sabado'].queryset = Sabado.objects.filter(pk=cfg.sabado_id)
    form.fields['sabado'].disabled = True

    formset = HorarioRondaFormSet(request.POST or None, instance=cfg, prefix='horarios')
    if request.method == 'POST' and formset.is_valid():
        formset.save()
        _reordenar_horarios(cfg)
        messages.success(request, 'Ronda atualizada! Se já havia sido sorteada, re-sorteie para aplicar.')
        return redirect('ronda:configuracao_detalhe', pk=cfg.pk)

    return render(request, 'form_configuracao.html', {
        'form': form, 'formset': formset, 'modo': 'editar', 'cfg': cfg,
    })


@ronda_required
def configuracao_deletar(request, pk):
    cfg = get_object_or_404(ConfiguracaoRondaSabado, pk=pk)
    if request.method == 'POST':
        # Se aprovada, estorna os pontos que a ronda somou (sem descer de 0).
        if cfg.status == 'APROVADA':
            ano = cfg.sabado.data.year
            for escala in EscalaRonda.objects.filter(horario__configuracao=cfg):
                ScoreRonda.objects.filter(
                    voluntario=escala.voluntario, ano=ano, pontos__gt=0
                ).update(pontos=F('pontos') - 1)
        cfg.delete()
        messages.success(request, 'Ronda excluída.')
        return redirect('ronda:painel')
    return redirect('ronda:configuracao_detalhe', pk=pk)


# ── Detalhe + ações ──────────────────────────────────────────────────────────

@ronda_required
def configuracao_detalhe(request, pk):
    cfg = get_object_or_404(ConfiguracaoRondaSabado, pk=pk)
    horarios = (
        cfg.horarios.select_related('local')
        .prefetch_related('escalas__voluntario')
        .order_by('hora_inicio', 'local__nome')
    )

    # Agrupa por janela de horário: [(label, [linha, ...]), ...]
    janelas = OrderedDict()
    for h in horarios:
        chave = (h.hora_inicio, h.hora_fim)
        janelas.setdefault(chave, []).append(h)

    grade = [
        {
            'inicio': chave[0],
            'fim': chave[1],
            'linhas': linhas,  # cada linha é um HorarioRonda (com .local e .escalas)
        }
        for chave, linhas in janelas.items()
    ]
    grade_evento = _grade_evento(horarios) if cfg.dia_de_evento else []

    from voluntario.models import Voluntario
    elegiveis = (
        Voluntario.objects.filter(data_saida__isnull=True)
        .exclude(area__in=AREAS_ISENTAS_RONDA)
        .order_by('first_name', 'last_name')
    )
    ano = cfg.sabado.data.year
    scores = {
        s.voluntario_id: s.pontos
        for s in ScoreRonda.objects.filter(voluntario__in=elegiveis, ano=ano)
    }
    ultima_ronda = _mapa_ultima_ronda()

    total_linhas = cfg.horarios.filter(local__isnull=False).count()
    confirmados = _contar_confirmados(cfg.sabado)
    por_linha = 4 if cfg.dia_de_evento else 2
    necessarios = total_linhas * por_linha

    return render(request, 'detalhe_configuracao.html', {
        'cfg': cfg,
        'grade': grade,
        'grade_evento': grade_evento,
        'elegiveis': elegiveis,
        'scores': scores,
        'ultima_ronda': ultima_ronda,
        'hoje': timezone.now().date(),
        'confirmados': confirmados,
        'necessarios': necessarios,
        'pool_insuficiente': confirmados < necessarios,
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
        ano = cfg.sabado.data.year
        for escala in EscalaRonda.objects.filter(horario__configuracao=cfg):
            ScoreRonda.incrementar(escala.voluntario, ano)
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
    if cfg.dia_de_evento:
        messages.error(request, 'Em dia de evento as duplas são fixas — re-sorteie se precisar mudar.')
        return redirect('ronda:configuracao_detalhe', pk=cfg.pk)
    if cfg.status not in ('SORTEADA', 'PENDENTE_SORTEIO'):
        messages.error(request, 'Só é possível trocar voluntários antes da aprovação.')
        return redirect('ronda:configuracao_detalhe', pk=cfg.pk)

    from voluntario.models import Voluntario
    novo_pk = request.POST.get('voluntario_novo_pk')
    if not novo_pk:
        messages.error(request, 'Selecione um voluntário para a troca.')
        return redirect('ronda:configuracao_detalhe', pk=cfg.pk)
    try:
        novo_vol = Voluntario.objects.get(pk=novo_pk, data_saida__isnull=True)
    except (Voluntario.DoesNotExist, ValueError):
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


# ── Impressão ────────────────────────────────────────────────────────────────

@ronda_required
def configuracao_imprimir(request, pk):
    cfg = get_object_or_404(ConfiguracaoRondaSabado, pk=pk)
    horarios = (
        cfg.horarios.select_related('local')
        .prefetch_related('escalas__voluntario')
        .order_by('hora_inicio', 'local__nome')
    )
    janelas = OrderedDict()
    for h in horarios:
        chave = (h.hora_inicio, h.hora_fim)
        janelas.setdefault(chave, []).append(h)
    grade = [
        {'inicio': chave[0], 'fim': chave[1], 'linhas': linhas}
        for chave, linhas in janelas.items()
    ]
    grade_evento = _grade_evento(horarios) if cfg.dia_de_evento else []
    return render(request, 'imprimir_ronda.html', {
        'cfg': cfg, 'grade': grade, 'grade_evento': grade_evento,
    })


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
        .prefetch_related('horarios__escalas__voluntario', 'horarios__local')
        .select_related('sabado')
        .order_by('-sabado__data')
    )

    # Para cada config, agrupa horários por janela de tempo
    blocos = []
    for cfg in configuracoes:
        horarios = sorted(
            cfg.horarios.all(),
            key=lambda h: (h.hora_inicio, h.local.nome if h.local_id else '')
        )
        janelas = OrderedDict()
        for h in horarios:
            janelas.setdefault((h.hora_inicio, h.hora_fim), []).append(h)
        grade = [
            {'inicio': chave[0], 'fim': chave[1], 'linhas': linhas}
            for chave, linhas in janelas.items()
        ]
        grade_evento = _grade_evento(horarios) if cfg.dia_de_evento else []
        blocos.append({'cfg': cfg, 'grade': grade, 'grade_evento': grade_evento})

    return render(request, 'ronda_publica.html', {'blocos': blocos})
