from django.utils.functional import SimpleLazyObject

from .services import mencoes_acessiveis


def notificacoes_mencoes(request):
    if not request.user.is_authenticated:
        return {}
    return {"total_mencoes_nao_lidas": SimpleLazyObject(
        lambda: mencoes_acessiveis(request.user).filter(lida_em__isnull=True).count()
    )}
