import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from sabado.models import Sabado
from .models import EscalaAjuda
from .permissions import triade_required
from .selectors import dados_quadro, quadro_publicado
from .services import ConflitoEdicao, reabrir_escala, salvar_escala


@triade_required
@require_GET
def painel(request):
    sabados = Sabado.objects.select_related("escala_ajudas").order_by("-data")
    return render(request, "ajudas/painel.html", {"sabados": sabados, "hoje": timezone.localdate()})


@triade_required
@never_cache
@require_GET
def organizar(request, sabado_id):
    sabado = get_object_or_404(Sabado, pk=sabado_id)
    return render(request, "ajudas/organizar.html", {"sabado": sabado, "quadro": dados_quadro(sabado)})


def _alterar(request, sabado_id, acao):
    sabado = get_object_or_404(Sabado, pk=sabado_id)
    try:
        dados = json.loads(request.body)
        if not isinstance(dados, dict):
            raise ValidationError("Envie um objeto com os dados da escala.")
        if acao == "reabrir":
            reabrir_escala(usuario=request.user, sabado_id=sabado.pk, dados=dados)
        else:
            salvar_escala(usuario=request.user, sabado_id=sabado.pk, dados=dados, publicar=acao == "publicar")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"erros": ["Não foi possível ler os dados enviados."]}, status=400)
    except ConflitoEdicao as erro:
        return JsonResponse({"erros": erro.messages}, status=409)
    except ValidationError as erro:
        return JsonResponse({"erros": erro.messages}, status=400)
    sabado.refresh_from_db()
    return JsonResponse({"quadro": dados_quadro(sabado)})


@triade_required
@require_POST
def salvar(request, sabado_id):
    return _alterar(request, sabado_id, "salvar")


@triade_required
@require_POST
def publicar(request, sabado_id):
    return _alterar(request, sabado_id, "publicar")


@triade_required
@require_POST
def reabrir(request, sabado_id):
    return _alterar(request, sabado_id, "reabrir")


@login_required
@never_cache
@require_GET
def escala_publicada(request, sabado_id=None):
    escalas = EscalaAjuda.objects.filter(status=EscalaAjuda.Status.PUBLICADA).select_related("sabado")
    if sabado_id is not None:
        escala = get_object_or_404(escalas, sabado_id=sabado_id)
    else:
        escala = (escalas.filter(sabado__data__gte=timezone.localdate()).order_by("sabado__data").first()
                  or escalas.order_by("-sabado__data").first())
    return render(request, "ajudas/escala.html", {
        "escala": escala, "escalas": escalas.order_by("-sabado__data"),
        "areas": quadro_publicado(escala) if escala else [],
    })
