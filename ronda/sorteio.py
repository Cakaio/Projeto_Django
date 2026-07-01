# ronda/sorteio.py
import random
from collections import defaultdict
from django.utils import timezone
from .models import AREAS_ISENTAS_RONDA, EscalaRonda, ScoreRonda


def executar_sorteio(configuracao):
    """
    Sorteia 2 voluntários por linha (HorarioRonda = faixa de horário + local),
    priorizando menor score anual. Um voluntário não pode aparecer duas vezes na
    mesma FAIXA DE HORÁRIO (mesmo início/fim), ainda que em locais diferentes.
    Só entram voluntários que confirmaram presença (vai_ao_projeto=True) no sábado.
    Deleta escalas anteriores desta configuração antes de re-sortear.
    """
    from voluntario.models import Voluntario
    from sabado.models import DisponibilidadeVoluntario

    ano = configuracao.sabado.data.year
    EscalaRonda.objects.filter(horario__configuracao=configuracao).delete()

    confirmados_ids = set(
        DisponibilidadeVoluntario.objects.filter(
            sabado=configuracao.sabado,
            vai_ao_projeto=True,
        ).values_list('voluntario_id', flat=True)
    )

    horarios = list(
        configuracao.horarios.select_related('local')
        .order_by('ordem', 'hora_inicio', 'local__nome')
    )

    # Controle de quem já foi alocado por janela de horário (início, fim)
    ja_alocados_por_janela = defaultdict(set)

    for horario in horarios:
        if horario.local_id is None:
            continue  # linha sem local definido — ignora

        janela = (horario.hora_inicio, horario.hora_fim)
        ja_alocados = ja_alocados_por_janela[janela]

        pool = list(
            Voluntario.objects.filter(data_saida__isnull=True, pk__in=confirmados_ids)
            .exclude(area__in=AREAS_ISENTAS_RONDA)
            .exclude(pk__in=ja_alocados)
        )
        if not pool:
            continue

        scores = {
            s.voluntario_id: s.pontos
            for s in ScoreRonda.objects.filter(voluntario__in=pool, ano=ano)
        }

        # Embaralha antes de ordenar — sort estável preserva aleatoriedade dentro do grupo
        random.shuffle(pool)
        pool.sort(key=lambda v: scores.get(v.pk, 0))

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
