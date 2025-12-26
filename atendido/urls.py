from django.urls import path, include
from .views import Homepage, DetalheAtendido

app_name = 'atendido'

urlpatterns = [
    path('', Homepage.as_view(), name='homepage'),
    path('<int:pk>/', DetalheAtendido.as_view(), name='detalhe_atendido'),
]