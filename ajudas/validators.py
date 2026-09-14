from datetime import time

from django.core.exceptions import ValidationError


def validar_periodo(inicio, fim, sabado):
    if not isinstance(inicio, time) or not isinstance(fim, time):
        return  # Os próprios TimeFields informam campos ausentes/inválidos.
    if inicio >= fim:
        raise ValidationError({"hora_fim": "O término deve ser posterior ao início."})
    if inicio < sabado.hora_inicio or fim > sabado.hora_fim:
        raise ValidationError("O horário deve estar dentro do período do sábado.")


def sobrepoe(inicio, fim, outro_inicio, outro_fim):
    """Intervalos semiabertos: terminar às 10h permite outra ajuda às 10h."""
    return inicio < outro_fim and fim > outro_inicio


def validar_participante(voluntario, area_destino, confirmado):
    if not voluntario.is_active or voluntario.data_saida is not None:
        raise ValidationError(f"{voluntario}: o voluntário precisa estar ativo no projeto.")
    if voluntario.area == area_destino:
        raise ValidationError(f"{voluntario}: permanecer na própria área não gera ajuda.")
    if not confirmado:
        raise ValidationError(f"{voluntario}: não confirmou presença neste sábado.")


def validar_conflitos(ajudas):
    por_voluntario = {}
    for ajuda in sorted(ajudas, key=lambda a: (a.voluntario_id, a.hora_inicio)):
        anterior = por_voluntario.get(ajuda.voluntario_id)
        if anterior and sobrepoe(ajuda.hora_inicio, ajuda.hora_fim,
                                 anterior.hora_inicio, anterior.hora_fim):
            raise ValidationError(f"{ajuda.voluntario}: há ajudas com horários sobrepostos.")
        por_voluntario[ajuda.voluntario_id] = ajuda
