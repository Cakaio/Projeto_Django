from django.urls import path

from . import views

app_name = "bazar"

urlpatterns = [
    # Atendimento: a tela da fila.
    path("", views.atendimento, name="atendimento"),
    path("buscar/", views.buscar_atendido, name="buscar"),
    path("situacao/<int:pk>/", views.situacao, name="situacao"),
    path("finalizar/", views.finalizar, name="finalizar"),
    # Coordenação.
    path("painel/", views.painel, name="painel"),
    path("<int:pk>/etapa/", views.mudar_etapa, name="mudar_etapa"),
    path("<int:pk>/relatorio/", views.relatorio, name="relatorio"),
]
