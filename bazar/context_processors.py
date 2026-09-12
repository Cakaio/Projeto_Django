"""O Bazar no menu, só enquanto estiver acontecendo.

Fora do evento, um item "Bazar" no menu de todo voluntário é peso morto o ano
inteiro. Aqui ele aparece quando há uma edição aberta e some quando encerra,
sem ninguém precisar lembrar de esconder.
"""
from django.utils.functional import SimpleLazyObject

from .models import Bazar


def bazar_aberto(request):
    if not request.user.is_authenticated:
        return {}
    return {"bazar_aberto": SimpleLazyObject(Bazar.em_andamento)}
