from django.urls import path

from . import views

app_name = "bazar"

urlpatterns = [
    # Atendimento: a tela da fila.
    path("", views.atendimento, name="atendimento"),
    path("buscar/", views.buscar_atendido, name="buscar"),
    path("situacao/<int:pk>/", views.situacao, name="situacao"),
    path("finalizar/", views.finalizar, name="finalizar"),
    path("cancelar/<int:pk>/", views.cancelar, name="cancelar"),
    # Coordenação.
    path("painel/", views.painel, name="painel"),
    path("<int:pk>/etapa/", views.mudar_etapa, name="mudar_etapa"),
    path("<int:pk>/relatorio/", views.relatorio, name="relatorio"),
    # O kit de papel e aberto a qualquer voluntario logado: quem esta no
    # caixa e que precisa imprimir.
    path("<int:pk>/kit/", views.kit_papel, name="kit_papel"),
    path("<int:pk>/kit.xlsx", views.kit_planilha, name="kit_planilha"),
]
