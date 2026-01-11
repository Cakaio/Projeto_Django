from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from .models import Semanario, COMPETENCIAS_SALAS

@require_GET
@csrf_exempt  # apenas para facilitar no admin; no frontend real é melhor manter com CSRF
def get_competencias(request):
    semanario_id = request.GET.get("semanario_id")
    sala = request.GET.get("sala")
    competencias = []

    if sala:
        competencias = COMPETENCIAS_SALAS.get(sala, [])
    elif semanario_id:
        try:
            semanario = Semanario.objects.get(id=semanario_id)
            competencias = COMPETENCIAS_SALAS.get(semanario.sala, [])
        except Semanario.DoesNotExist:
            pass

    return JsonResponse({"competencias": competencias})
