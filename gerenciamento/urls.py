from django.urls import path

from . import views

app_name = "gerenciamento"

urlpatterns = [
    path("", views.pautas, name="pautas"),
    path("nova/", views.criar_pauta, name="criar_pauta"),
    path("minhas/", views.minhas_pautas, name="minhas_pautas"),
    path("<int:pk>/editar/", views.editar_pauta, name="editar_pauta"),
    path("<int:pk>/ciencia/", views.alternar_ciencia_pauta, name="alternar_ciencia"),
    path("<int:pk>/comentar/", views.comentar_pauta, name="comentar_pauta"),
]
