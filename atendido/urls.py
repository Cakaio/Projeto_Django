from django.urls import path, include
from .views import Homepage, DetalheAtendido, registrar_presencas

app_name = 'atendido'

urlpatterns = [
    path('', Homepage.as_view(), name='lista_atendidos'),
    path('presencas/', registrar_presencas, name='registrar_presencas'),
    path('<int:pk>/', DetalheAtendido.as_view(), name='detalhe_atendido'),
]
