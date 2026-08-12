from django.urls import path
from . import views
from forms_pcf import views as forms_views

app_name = 'adm'

urlpatterns = [
    path('', views.painel, name='painel'),
    path('lancamentos/', views.lista_lancamentos, name='lista_lancamentos'),
    path('lancamentos/novo/', views.criar_lancamento, name='criar_lancamento'),
    path('lancamentos/<int:pk>/editar/', views.editar_lancamento, name='editar_lancamento'),
    path('lancamentos/<int:pk>/deletar/', views.deletar_lancamento, name='deletar_lancamento'),
    path('categorias/', views.lista_categorias, name='lista_categorias'),
    path('categorias/nova/', views.criar_categoria, name='criar_categoria'),
    path('categorias/<int:pk>/editar/', views.editar_categoria, name='editar_categoria'),
    path('categorias/<int:pk>/deletar/', views.deletar_categoria, name='deletar_categoria'),
    path('fluxo-de-caixa/', views.fluxo_caixa, name='fluxo_caixa'),
    path('dre/', views.dre, name='dre'),
    path('onde-investimos/', views.onde_investimos, name='onde_investimos'),
    path('notificacoes-reembolso/', forms_views.receptores_reembolso, name='receptores_reembolso'),
    path('notificacoes-reembolso/novo/', forms_views.receptor_criar, name='receptor_criar'),
    path('notificacoes-reembolso/<int:pk>/editar/', forms_views.receptor_editar, name='receptor_editar'),
    path('notificacoes-reembolso/<int:pk>/deletar/', forms_views.receptor_deletar, name='receptor_deletar'),
]
