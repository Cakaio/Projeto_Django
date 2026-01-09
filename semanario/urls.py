from django.urls import path, include
from .views import SemanarioCreateView

app_name = 'semanario'

urlpatterns = [
    ##path('', AtendidoView.as_view(), name='atendido_view'),
    path('criarsemanario/', SemanarioCreateView.as_view(), name='criar_semanario'),
]
