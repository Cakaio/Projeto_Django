from django.urls import path

from . import views

app_name = 'parceiros'

urlpatterns = [
    path('', views.painel, name='painel'),
    path('grade/', views.grade, name='grade'),
    path('lista/', views.lista, name='lista'),
    path('novo/', views.parceiro_form, name='criar'),
    path('<int:pk>/', views.ficha, name='ficha'),
    path('<int:pk>/editar/', views.parceiro_form, name='editar'),
    path('<int:pk>/excluir/', views.parceiro_deletar, name='excluir'),
    path('contribuicoes/nova/', views.contribuicao_form, name='contribuicao_criar'),
    path('contribuicoes/<int:pk>/editar/', views.contribuicao_form, name='contribuicao_editar'),
    path('contribuicoes/<int:pk>/excluir/', views.contribuicao_deletar, name='contribuicao_excluir'),
]
