from django.urls import path, include
from . import views_ajax
from .views import criar_semanario, adicionar_material

app_name = 'semanario'

urlpatterns = [
    ##path('', AtendidoView.as_view(), name='atendido_view'),
    path('novo/', criar_semanario, name='criar_semanario'),
    path("ajax/get_competencias/", views_ajax.get_competencias, name="get_competencias"),
    path("adicionar-material/<int:atividade_id>/", adicionar_material, name="adicionar_material"),
]
