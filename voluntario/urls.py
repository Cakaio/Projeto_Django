from django.urls import path

from semanario import views
from .views import (
    MeuPerfilView, VoluntarioView, ListaVoluntario, RegistrarPresencasVoluntarios,
    visualizar_presencas_voluntarios, saas_view, criar_ocorrencia,
    historico_ocorrencias, deletar_ocorrencia,
)
from django.contrib.auth import views as auth_views

app_name = 'voluntario'

urlpatterns = [
    path('', VoluntarioView.as_view(), name='voluntario_view'),
    path('matriculados/', ListaVoluntario.as_view(), name='lista_voluntarios'),
    path('presencas/', RegistrarPresencasVoluntarios, name='registrar_presencas'),
    path("meu-perfil/", MeuPerfilView.as_view(), name="meu_perfil"),
    path("alterar_senha/",auth_views.PasswordChangeView.as_view(template_name="alterar_senha.html",success_url="/voluntario/alterar_senha/sucesso/"),name="alterar_senha"),
    path("alterar_senha/sucesso/",auth_views.PasswordChangeDoneView.as_view(template_name="alterar_senha_sucesso.html"),name="alterar_senha_sucesso"),
    path("visualizar-presencas-voluntarios/",visualizar_presencas_voluntarios,name="visualizar_presencas_voluntarios"),
    path("saas/", saas_view, name="saas"),
    path("saas/ocorrencia/", criar_ocorrencia, name="criar_ocorrencia"),
    path("saas/historico/<pk>/", historico_ocorrencias, name="historico_ocorrencias"),
    path("saas/ocorrencia/<uuid:ocorrencia_id>/deletar/", deletar_ocorrencia, name="deletar_ocorrencia"),
]