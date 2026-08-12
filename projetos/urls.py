from django.urls import path

from . import views

app_name = 'projetos'

urlpatterns = [
    path('', views.backlog, name='backlog'),
    path('areas/', views.por_area, name='por_area'),
    path('nova/', views.criar, name='criar'),
    path('registro/<int:pk>/deletar/', views.registro_deletar, name='registro_deletar'),
    path('<int:pk>/', views.ficha, name='ficha'),
    path('<int:pk>/editar/', views.editar, name='editar'),
    path('<int:pk>/deletar/', views.deletar, name='deletar'),
]
