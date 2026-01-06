from django.urls import path
from .views import VoluntarioView, ListaVoluntario, RegistrarPresencasVoluntarios

app_name = 'voluntario'

urlpatterns = [
    path('', VoluntarioView.as_view(), name='voluntario_view'),
    path('matriculados/', ListaVoluntario.as_view(), name='lista_voluntarios'),
    path('presencas/', RegistrarPresencasVoluntarios, name='registrar_presencas'),
]