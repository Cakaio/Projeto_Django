from django.urls import path
from . import views

app_name = 'supply'

urlpatterns = [
    path('', views.ListaItensView.as_view(), name='lista_itens'),
    path('movimentacoes/', views.ListaMovimentacoesView.as_view(), name='lista_movimentacoes'),
]
