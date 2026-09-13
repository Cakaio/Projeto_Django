"""Alterações completas da escala: validar, gravar e publicar na mesma transação."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from sabado.models import DisponibilidadeVoluntario, Sabado
from voluntario.models import Voluntario
from .forms import AjudaForm, EscalaForm, NecessidadeForm, RevisaoForm
from .models import Ajuda, EscalaAjuda, NecessidadeAjuda
from .permissions import exigir_triade
from .validators import validar_conflitos, validar_participante, validar_periodo, sobrepoe


class ConflitoEdicao(ValidationError):
    pass


def _validar_form(form, rotulo):
    # JSON pode trazer listas/objetos onde widgets de formulário esperam
    # escalares; TimeField do Django chama .strip() antes de validar.
    for campo in form.fields:
        valor = form.data.get(campo)
        if valor is not None and (isinstance(valor, bool) or not isinstance(valor, (str, int, float))):
            raise ValidationError(f"{rotulo} · {campo}: valor inválido.")
        if campo in ("hora_inicio", "hora_fim") and valor is not None and not isinstance(valor, str):
            raise ValidationError(f"{rotulo} · {campo}: informe um horário no formato HH:MM.")
    if not form.is_valid():
        raise ValidationError([f"{rotulo} · {campo}: {erro}"
                               for campo, erros in form.errors.items() for erro in erros])
    return form.cleaned_data


def _linhas(dados, chave, form_class):
    linhas = dados.get(chave)
    if not isinstance(linhas, list) or len(linhas) > 2000:
        raise ValidationError(f"Envie uma lista válida de {chave} (até 2000 registros).")
    resultado = []
    for i, linha in enumerate(linhas, 1):
        if not isinstance(linha, dict):
            raise ValidationError(f"{chave} · linha {i} inválida.")
        resultado.append(_validar_form(form_class(linha), f"{chave} · linha {i}"))
    return resultado


def _conferir_revisao(escala, revisao):
    if revisao != (escala.revisao if escala else 0):
        raise ConflitoEdicao("Outra pessoa alterou esta escala. Recarregue a página antes de continuar.")


@transaction.atomic
def salvar_escala(*, usuario, sabado_id, dados, publicar=False):
    exigir_triade(usuario)
    cabecalho = _validar_form(EscalaForm(dados), "Sábado")
    necessidades_dados = _linhas(dados, "necessidades", NecessidadeForm)
    ajudas_dados = _linhas(dados, "ajudas", AjudaForm)
    # Trava também o caso da PRIMEIRA escala, quando não há linha para bloquear.
    sabado = Sabado.objects.select_for_update().get(pk=sabado_id)
    escala = EscalaAjuda.objects.filter(sabado=sabado).first()
    _conferir_revisao(escala, cabecalho["revisao"])
    if escala and escala.status == EscalaAjuda.Status.PUBLICADA:
        raise ConflitoEdicao("Reabra a escala publicada antes de editá-la.")

    sabado.hora_inicio = cabecalho["hora_inicio"]
    sabado.hora_fim = cabecalho["hora_fim"]
    validar_periodo(sabado.hora_inicio, sabado.hora_fim, sabado)
    necessidades = [NecessidadeAjuda(**linha) for linha in necessidades_dados]
    por_area = {}
    for n in necessidades:
        validar_periodo(n.hora_inicio, n.hora_fim, sabado)
        for outra in por_area.setdefault(n.area, []):
            if sobrepoe(n.hora_inicio, n.hora_fim, outra.hora_inicio, outra.hora_fim):
                raise ValidationError(f"{n.get_area_display()}: necessidades com horários sobrepostos.")
        por_area[n.area].append(n)

    ids = {linha["voluntario"] for linha in ajudas_dados}
    voluntarios = {v.pk: v for v in Voluntario.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    confirmados = set(DisponibilidadeVoluntario.objects.select_for_update().filter(
        sabado=sabado, voluntario_id__in=ids, vai_ao_projeto=True
    ).values_list("voluntario_id", flat=True))
    ajudas = []
    for linha in ajudas_dados:
        voluntario = voluntarios.get(linha["voluntario"])
        if not voluntario:
            raise ValidationError("Um dos voluntários informados não existe.")
        ajuda = Ajuda(voluntario=voluntario, **{k: v for k, v in linha.items() if k != "voluntario"})
        validar_periodo(ajuda.hora_inicio, ajuda.hora_fim, sabado)
        validar_participante(voluntario, ajuda.area_destino, voluntario.pk in confirmados)
        if not any(n.hora_inicio <= ajuda.hora_inicio and n.hora_fim >= ajuda.hora_fim
                   for n in por_area.get(ajuda.area_destino, [])):
            raise ValidationError(f"{voluntario}: a ajuda deve caber em uma necessidade da área destino.")
        ajudas.append(ajuda)
    validar_conflitos(ajudas)

    # A validação considera o conjunto novo, permitindo ajustar o período e as
    # alocações juntos. Nada é perdido se qualquer linha falhar.
    Sabado.objects.filter(pk=sabado.pk).update(hora_inicio=sabado.hora_inicio, hora_fim=sabado.hora_fim)
    if escala is None:
        escala = EscalaAjuda(sabado=sabado)
    else:
        escala.revisao += 1
    escala.status = EscalaAjuda.Status.PUBLICADA if publicar else EscalaAjuda.Status.RASCUNHO
    escala.publicada_em = timezone.now() if publicar else None
    escala.save()
    escala.ajudas.all().delete()
    escala.necessidades.all().delete()
    for objeto in necessidades + ajudas:
        objeto.escala = escala
    # Dados já validados em lote, sem consultas repetidas por voluntário.
    NecessidadeAjuda.objects.bulk_create(necessidades)
    Ajuda.objects.bulk_create(ajudas)
    return escala


@transaction.atomic
def reabrir_escala(*, usuario, sabado_id, dados):
    exigir_triade(usuario)
    revisao = _validar_form(RevisaoForm(dados), "Escala")["revisao"]
    sabado = Sabado.objects.select_for_update().get(pk=sabado_id)
    escala = EscalaAjuda.objects.filter(sabado=sabado).first()
    _conferir_revisao(escala, revisao)
    if not escala or escala.status != EscalaAjuda.Status.PUBLICADA:
        raise ValidationError("Somente uma escala publicada pode ser reaberta.")
    escala.status = EscalaAjuda.Status.RASCUNHO
    escala.publicada_em = None
    escala.revisao += 1
    escala.save(update_fields=["status", "publicada_em", "revisao", "atualizado_em"])
    return escala
