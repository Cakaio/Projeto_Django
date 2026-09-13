from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def exigir_triade(usuario):
    if not usuario.is_authenticated or not usuario.is_active or usuario.area != "TRIADE":
        raise PermissionDenied("Somente a Tríade pode organizar as ajudas.")


def triade_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        exigir_triade(request.user)
        return view(request, *args, **kwargs)
    return wrapper
