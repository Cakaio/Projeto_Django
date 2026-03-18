from django.urls import path
from . import views
from .views import painel_materiais

app_name = 'supply'

urlpatterns = [
    path('', views.ListaItensView.as_view(), name='lista_itens'),
    path('movimentacoes/', views.ListaMovimentacoesView.as_view(), name='lista_movimentacoes'),
    path("painel_materiais/", painel_materiais, name="painel_materiais"),
    path("painel_materiais/salvar-lote/", views.salvar_materiais_lote, name="salvar_materiais_lote"),
    path("painel_materiais/visualizacao/", views.painel_materiais_visualizacao, name="painel_materiais_visualizacao"),
]
