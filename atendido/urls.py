from django.urls import path, include
from .views import ListaAtendido, DetalheAtendido, RegistrarPresencasAtendidos, AtendidoView
from atendido import views

app_name = 'atendido'

urlpatterns = [
    path('', AtendidoView.as_view(), name='atendido_view'),
    path('matricula/', views.matricula_atendido, name='matricula'),
    path('matricula/<int:pk>/editar/', views.matricula_atendido, name='matricula_editar'),
    path('matricula/buscar-responsaveis/', views.buscar_responsaveis, name='buscar_responsaveis'),
    path('matricula/buscar-familias/', views.buscar_familias, name='buscar_familias'),
    path('lista-espera/cadastrar/', views.cadastrar_lista_espera, name='cadastrar_lista_espera'),
    path('lista-espera/', views.visualizar_lista_espera, name='visualizar_lista_espera'),
    path('matriculados', ListaAtendido.as_view(), name='lista_atendidos'),
    path('presencas/', RegistrarPresencasAtendidos, name='registrar_presencas'),
    path('<int:pk>/', DetalheAtendido.as_view(), name='detalhe_atendido'),
    path("visualizar-presencas/",views.visualizar_presencas_atendidos,name="visualizar_presencas_atendidos"),
]
