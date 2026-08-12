from django.urls import path

from . import views

app_name = 'editais'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('novo/', views.criar, name='criar'),
    path('fontes/', views.fontes, name='fontes'),
    path('fontes/nova/', views.fonte_form, name='fonte_criar'),
    path('fontes/<int:pk>/editar/', views.fonte_form, name='fonte_editar'),
    path('fontes/<int:pk>/deletar/', views.fonte_deletar, name='fonte_deletar'),
    path('palavras/', views.palavras, name='palavras'),
    path('<int:pk>/editar/', views.editar, name='editar'),
    path('<int:pk>/deletar/', views.deletar, name='deletar'),
]
