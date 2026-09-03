from django.urls import path

from . import views

app_name = 'estudio'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('novo/', views.criar, name='criar'),
    path('<int:pk>/', views.editor, name='editor'),
    path('<int:pk>/ver/', views.ver, name='ver'),
    path('<int:pk>/imprimir/', views.imprimir, name='imprimir'),
    path('<int:pk>/apagar/', views.apagar, name='apagar'),

    path('<int:pk>/pagina/nova/', views.pagina_nova, name='pagina_nova'),
    path('<int:pk>/pagina/<int:pagina_pk>/salvar/', views.salvar_pagina, name='salvar_pagina'),
    path('<int:pk>/pagina/<int:pagina_pk>/apagar/', views.pagina_apagar, name='pagina_apagar'),
    path('<int:pk>/pagina/<int:pagina_pk>/mover/', views.pagina_mover, name='pagina_mover'),

    path('assets/', views.assets, name='assets'),
    path('assets/novo/', views.asset_novo, name='asset_novo'),

    path('revista/<int:revista_pk>/gerar/', views.gerar_da_revista, name='gerar_da_revista'),
]
