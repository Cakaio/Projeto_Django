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
    path('contas/', views.contas, name='contas'),
    path('contas/nova/', views.conta_form, name='conta_criar'),
    path('contas/recargas/', views.recargas, name='recargas'),
    path('contas/recargas/nova/', views.recarga_form, name='recarga_criar'),
    path('contas/recargas/<int:pk>/editar/', views.recarga_form, name='recarga_editar'),
    path('contas/<int:pk>/editar/', views.conta_form, name='conta_editar'),
    path('tetos/', views.tetos, name='tetos'),
    path('tetos/novo/', views.teto_form, name='teto_criar'),
    path('tetos/<int:pk>/editar/', views.teto_form, name='teto_editar'),
    path('reembolsos/', views.reembolsos, name='reembolsos'),
    path('reembolsos/<int:pk>/pagar/', views.reembolso_pagar, name='reembolso_pagar'),
    path('notificacoes-reembolso/', forms_views.receptores_reembolso, name='receptores_reembolso'),
    path('notificacoes-reembolso/novo/', forms_views.receptor_criar, name='receptor_criar'),
    path('notificacoes-reembolso/<int:pk>/editar/', forms_views.receptor_editar, name='receptor_editar'),
    path('notificacoes-reembolso/<int:pk>/deletar/', forms_views.receptor_deletar, name='receptor_deletar'),
]
