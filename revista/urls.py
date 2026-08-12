"""Rotas da revista.

ATENÇÃO PARA QUEM INTEGRA: este módulo é montado na RAIZ, não em 'revista/':

    path('', include('revista.urls', namespace='revista')),

O prefixo já está escrito em cada rota aqui dentro. É de propósito: a página do
doador mora em `/r/<token>/` (link curto, para colar em e-mail e WhatsApp) e
precisa ficar fora de `/revista/`, mas no MESMO namespace das outras — dois
`include` com o namespace 'revista' fariam um sobrescrever o outro no reverse.
"""
from django.urls import path

from . import views

app_name = 'revista'

urlpatterns = [
    path('revista/', views.lista, name='lista'),
    path('revista/nova/', views.criar, name='criar'),
    path('revista/<int:pk>/', views.ver, name='ver'),
    path('revista/<int:pk>/editar/', views.editar, name='editar'),
    path('revista/<int:pk>/montar/', views.montar, name='montar'),
    path('revista/<int:pk>/pdf/', views.pdf, name='pdf'),
    path('revista/<int:pk>/email/', views.email_html, name='email_html'),
    path('revista/<int:pk>/publicar/', views.publicar, name='publicar'),
    path('revista/<int:pk>/deletar/', views.deletar, name='deletar'),

    # Link do doador: sem login, só o token.
    path('r/<str:token>/', views.publica, name='publica'),
]
