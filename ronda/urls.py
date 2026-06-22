# ronda/urls.py
from django.urls import path
from . import views

app_name = 'ronda'

urlpatterns = [
    # Gestão (restrito Tríade)
    path('painel/',                               views.painel,               name='painel'),
    path('locais/',                               views.locais,               name='locais'),
    path('locais/novo/',                          views.local_criar,          name='local_criar'),
    path('locais/<int:pk>/editar/',               views.local_editar,         name='local_editar'),
    path('locais/<int:pk>/deletar/',              views.local_deletar,        name='local_deletar'),
    path('configuracoes/nova/',                   views.configuracao_criar,   name='configuracao_criar'),
    # Detalhe e ações (adicionadas na Task 4)
    # Ranking e score (adicionados na Task 5)
    # Pública (adicionada na Task 5)
]
