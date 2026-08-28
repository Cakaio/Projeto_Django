# ronda/sorteio.py
import random
from collections import defaultdict
from django.utils import timezone
from .models import AREAS_ISENTAS_RONDA, EscalaRonda, ScoreRonda


def _pool_confirmados(configuracao):
    """IDs de voluntários que confirmaram presença no sábado."""
    from sabado.models import DisponibilidadeVoluntario
    return set(
        DisponibilidadeVoluntario.objects.filter(
            sabado=configuracao.sabado, vai_ao_projeto=True,
        ).values_list('voluntario_id', flat=True)
    )


def _ordenar_por_score(pool, ano):
    """Embaralha e ordena por menor score anual (sort estável preserva o aleatório)."""
    scores = {
        s.voluntario_id: s.pontos
        for s in ScoreRonda.objects.filter(voluntario__in=pool, ano=ano)
    }
    random.shuffle(pool)
    pool.sort(key=lambda v: scores.get(v.pk, 0))


def executar_sorteio(configuracao):
    """
    Sorteia a escala de ronda.

    Modo normal: 2 voluntários por linha (horário + local); um voluntário não se
    repete na mesma faixa de horário.

    Modo dia de evento: 2 grupos fixos por local (grupo 1 e grupo 2), com o
    tamanho definido em cada local (`pessoas_por_grupo`: 2 = duplas, 3 = trios);
    cada voluntário aparece em um único local.

    Em ambos: só entram quem confirmou presença (vai_ao_projeto=True), priorizando
    menor score anual. Deleta escalas anteriores antes de re-sortear.
    """
    from voluntario.models import Voluntario

    ano = configuracao.sabado.data.year
    EscalaRonda.objects.filter(horario__configuracao=configuracao).delete()
    confirmados_ids = _pool_confirmados(configuracao)

    horarios = list(
        configuracao.horarios.select_related('local')
        .order_by('ordem', 'hora_inicio', 'local__nome')
    )

    def _base_qs(excluir_ids):
        return list(
            Voluntario.objects.filter(data_saida__isnull=True, pk__in=confirmados_ids)
            .exclude(area__in=AREAS_ISENTAS_RONDA)
            .exclude(pk__in=excluir_ids)
        )

    if configuracao.dia_de_evento:
        # 2 grupos fixos por local (tamanho por local), cada pessoa em um único local
        ja_global = set()
        for horario in horarios:
            if horario.local_id is None:
                continue
            pool = _base_qs(ja_global)
            if not pool:
                continue
            _ordenar_por_score(pool, ano)
            tamanho = horario.local.pessoas_por_grupo or 2
            escolhidos = pool[:tamanho * 2]
            for i, vol in enumerate(escolhidos):
                EscalaRonda.objects.create(
                    horario=horario,
                    local=horario.local,
                    voluntario=vol,
                    dupla=1 if i < tamanho else 2,
                    is_substituto=False,
                )
                ja_global.add(vol.pk)
    else:
        # 2 por linha, sem repetir na mesma faixa de horário
        ja_alocados_por_janela = defaultdict(set)
        for horario in horarios:
            if horario.local_id is None:
                continue
            janela = (horario.hora_inicio, horario.hora_fim)
            ja_alocados = ja_alocados_por_janela[janela]
            pool = _base_qs(ja_alocados)
            if not pool:
                continue
            _ordenar_por_score(pool, ano)
            for vol in pool[:2]:
                EscalaRonda.objects.create(
                    horario=horario,
                    local=horario.local,
                    voluntario=vol,
                    is_substituto=False,
                )
                ja_alocados.add(vol.pk)

    configuracao.status = 'SORTEADA'
    configuracao.sorteado_em = timezone.now()
    configuracao.save(update_fields=['status', 'sorteado_em'])
