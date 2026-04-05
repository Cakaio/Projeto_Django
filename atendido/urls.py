from django.urls import path, include
from .views import ListaAtendido, DetalheAtendido, RegistrarPresencasAtendidos, AtendidoView
from atendido import views

app_name = 'atendido'

urlpatterns = [
    path('', AtendidoView.as_view(), name='atendido_view'),
    path('matriculados', ListaAtendido.as_view(), name='lista_atendidos'),
    path('presencas/', RegistrarPresencasAtendidos, name='registrar_presencas'),
    path('<int:pk>/', DetalheAtendido.as_view(), name='detalhe_atendido'),
    path("visualizar-presencas/",views.visualizar_presencas_atendidos,name="visualizar_presencas_atendidos"),
]
