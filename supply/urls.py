from django.urls import path
from . import views
from .views import adicionar_pedidos, painel_materiais, meus_pedidos

app_name = 'supply'

urlpatterns = [
    path('', views.SupplyView.as_view(), name='supply_view'),
    path('estoque/', views.ListaItensView.as_view(), name='lista_itens'),
    path('movimentacoes/', views.ListaMovimentacoesView.as_view(), name='lista_movimentacoes'),
    path("painel_materiais/", painel_materiais, name="painel_materiais"),
    path("painel_materiais/salvar-lote/", views.salvar_materiais_lote, name="salvar_materiais_lote"),
    path("painel_materiais/gerenciar-item/", views.gerenciar_item_painel, name="gerenciar_item_painel"),
    path("painel_materiais/visualizacao/", views.painel_materiais_visualizacao, name="painel_materiais_visualizacao"),
    path("pedidos/adicionar/", adicionar_pedidos, name="adicionar_pedidos"),
    path("meus_pedidos/", meus_pedidos, name="meus_pedidos"),
]
