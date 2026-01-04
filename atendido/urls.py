from django.urls import path, include
from .views import ListaAtendido, DetalheAtendido, registrar_presencas, AtendidoView

app_name = 'atendido'

urlpatterns = [
    path('', AtendidoView.as_view(), name='atendido_view'),
    path('matriculados', ListaAtendido.as_view(), name='lista_atendidos'),
    path('presencas/', registrar_presencas, name='registrar_presencas'),
    path('<int:pk>/', DetalheAtendido.as_view(), name='detalhe_atendido'),
]
