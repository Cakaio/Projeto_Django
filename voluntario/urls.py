from django.urls import path

from semanario import views
from .views import (
    MeuPerfilView, VoluntarioView, ListaVoluntario, RegistrarPresencasVoluntarios,
    visualizar_presencas_voluntarios, saas_view, criar_ocorrencia,
    historico_ocorrencias, deletar_ocorrencia, organograma, organograma_fullscreen, historico_lideres,
    grupos, grupo_form, excluir_grupo,
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
    path("organograma/", organograma, name="organograma"),
    path("organograma/tela-cheia/", organograma_fullscreen, name="organograma_fullscreen"),
    path("lideres/", historico_lideres, name="historico_lideres"),
    path("grupos/", grupos, name="grupos"),
    path("grupos/novo/", grupo_form, name="criar_grupo"),
    path("grupos/<int:pk>/editar/", grupo_form, name="editar_grupo"),
    path("grupos/<int:pk>/excluir/", excluir_grupo, name="excluir_grupo"),
]
