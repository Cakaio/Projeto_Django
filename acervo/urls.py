from django.urls import path

from . import views

app_name = 'acervo'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('colecao/nova/', views.colecao_form, name='colecao_criar'),
    path('colecao/<int:pk>/editar/', views.colecao_form, name='colecao_editar'),
    path('documento/novo/', views.documento_form, name='documento_criar'),
    path('documento/<int:pk>/editar/', views.documento_form, name='documento_editar'),
    path('documento/<int:pk>/apagar/', views.documento_deletar, name='documento_deletar'),
    # Por último: `<slug>` casaria com "colecao" e "documento" e engoliria as
    # rotas acima se viesse antes.
    path('<slug:slug>/', views.colecao, name='colecao'),
]
