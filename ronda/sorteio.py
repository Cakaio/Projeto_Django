# ronda/sorteio.py
import random
from django.utils import timezone
from .models import AREAS_ISENTAS_RONDA, EscalaRonda, LocalRonda, ScoreRonda


def executar_sorteio(configuracao):
    """
    Sorteia 2 voluntários por (HorarioRonda × LocalRonda) priorizando menor score anual.
    Um voluntário não pode aparecer duas vezes no mesmo horário.
    Deleta escalas anteriores desta configuração antes de re-sortear.
    """
    from voluntario.models import Voluntario
    from sabado.models import DisponibilidadeVoluntario

    ano_atual = timezone.now().year
    EscalaRonda.objects.filter(horario__configuracao=configuracao).delete()

    confirmados_ids = set(
        DisponibilidadeVoluntario.objects.filter(
            sabado=configuracao.sabado,
            vai_ao_projeto=True,
        ).values_list('voluntario_id', flat=True)
    )

    locais = list(LocalRonda.objects.filter(ativo=True))

    for horario in configuracao.horarios.order_by('ordem', 'hora_inicio'):
        ja_alocados_ids = set()

        for local in locais:
            pool = list(
                Voluntario.objects.filter(data_saida__isnull=True, pk__in=confirmados_ids)
                .exclude(area__in=AREAS_ISENTAS_RONDA)
                .exclude(pk__in=ja_alocados_ids)
            )

            if not pool:
                continue

            scores = {
                s.voluntario_id: s.pontos
                for s in ScoreRonda.objects.filter(voluntario__in=pool, ano=ano_atual)
            }

            # Embaralha antes de ordenar — sort estável preserva aleatoriedade dentro do grupo
            random.shuffle(pool)
            pool.sort(key=lambda v: scores.get(v.pk, 0))

            for vol in pool[:2]:
                EscalaRonda.objects.create(
                    horario=horario,
                    local=local,
                    voluntario=vol,
                    is_substituto=False,
                )
                ja_alocados_ids.add(vol.pk)

    configuracao.status = 'SORTEADA'
    configuracao.sorteado_em = timezone.now()
    configuracao.save(update_fields=['status', 'sorteado_em'])
