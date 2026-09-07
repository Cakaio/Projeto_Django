from django.urls import path

from . import views

app_name = "gerenciamento"

urlpatterns = [
    path("", views.pautas, name="pautas"),
    path("nova/", views.criar_pauta, name="criar_pauta"),
    path("minhas/", views.minhas_pautas, name="minhas_pautas"),
    path("mencoes/", views.mencoes, name="mencoes"),
    path("materiais/<int:pk>/baixar/", views.baixar_material, name="baixar_material"),
    path("<int:pk>/ciencias/", views.ciencias_pauta, name="ciencias_pauta"),
    path("<int:pk>/materiais/", views.adicionar_materiais, name="adicionar_materiais"),
    path("<int:pk>/mencoes/lidas/", views.ler_mencoes, name="ler_mencoes"),
    path("reunioes/nova/", views.criar_reuniao, name="criar_reuniao"),
    path(
        "reunioes/<int:pk>/painel/",
        views.painel_reuniao,
        name="painel_reuniao",
    ),
    path(
        "reunioes/<int:pk>/estado/",
        views.estado_reuniao,
        name="estado_reuniao",
    ),
    path("<int:pk>/editar/", views.editar_pauta, name="editar_pauta"),
    path("<int:pk>/ciencia/", views.registrar_ciencia_pauta, name="registrar_ciencia"),
    path("<int:pk>/comentar/", views.comentar_pauta, name="comentar_pauta"),
    path("<int:pk>/status/", views.atualizar_status_pauta, name="atualizar_status"),
]
