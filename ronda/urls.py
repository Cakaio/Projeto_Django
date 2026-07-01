# ronda/urls.py
from django.urls import path
from . import views

app_name = 'ronda'

urlpatterns = [
    # Gestão (restrito Tríade)
    path('painel/',                                        views.painel,                   name='painel'),
    path('locais/',                                        views.locais,                   name='locais'),
    path('locais/novo/',                                   views.local_criar,              name='local_criar'),
    path('locais/<int:pk>/editar/',                        views.local_editar,             name='local_editar'),
    path('locais/<int:pk>/deletar/',                       views.local_deletar,            name='local_deletar'),
    path('configuracoes/nova/',                            views.configuracao_criar,       name='configuracao_criar'),
    path('configuracoes/<int:pk>/',                        views.configuracao_detalhe,     name='configuracao_detalhe'),
    path('configuracoes/<int:pk>/editar/',                 views.configuracao_editar,      name='configuracao_editar'),
    path('configuracoes/<int:pk>/deletar/',                views.configuracao_deletar,     name='configuracao_deletar'),
    path('configuracoes/<int:pk>/imprimir/',               views.configuracao_imprimir,    name='configuracao_imprimir'),
    path('configuracoes/<int:pk>/sortear/',                views.configuracao_sortear,     name='configuracao_sortear'),
    path('configuracoes/<int:pk>/aprovar/',                views.configuracao_aprovar,     name='configuracao_aprovar'),
    path('configuracoes/<int:pk>/reprovar/',               views.configuracao_reprovar,    name='configuracao_reprovar'),
    path('escalas/<int:pk>/swap/',                         views.escala_swap,              name='escala_swap'),
    # Ranking e score
    path('ranking/',                                        views.ranking,                  name='ranking'),
    path('scores/<int:pk>/editar/',                         views.score_editar,             name='score_editar'),
    # Pública
    path('sabado/',                                         views.ronda_publica,            name='ronda_publica'),
]
