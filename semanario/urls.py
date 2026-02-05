from django.urls import path, include
from . import views_ajax
from .views import criar_semanario, adicionar_material, SemanarioListView, SemanarioView, editar_semanario, listar_materiais, painel_sabado_educ, salvar_materiais, VisualizarSemanario

app_name = 'semanario'

urlpatterns = [
    path('', SemanarioView.as_view(), name='semanario_view'),
    path('novo/', criar_semanario, name='criar_semanario'),
    path("ajax/get_competencias/", views_ajax.get_competencias, name="get_competencias"),
    path("adicionar-material/<int:atividade_id>/", adicionar_material, name="adicionar_material"),
    path("editar/<int:semanario_id>/", editar_semanario, name="editar_semanario"),
    path("visualizar/<int:semanario_id>/", VisualizarSemanario.as_view(), name="visualizar_semanario"),
    path("lista/", SemanarioListView.as_view(), name="lista_semanarios"),
    path("salvar_materiais/", salvar_materiais, name="salvar_materiais"),
    path("materiais/<int:atividade_id>/", listar_materiais, name="listar_materiais"),
    path("painel/", painel_sabado_educ, name="painel_sabado_educ"),
]
