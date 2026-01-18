from django.urls import path
from .views import responder_disponibilidade

app_name = 'sabado'

urlpatterns = [
    # Defina suas URLs aqui quando necessário
    path("responder/<int:sabado_id>/", responder_disponibilidade, name="responder_disponibilidade"),
]