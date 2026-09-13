from django.urls import path
from . import views

app_name = "ajudas"
urlpatterns = [
    path("", views.escala_publicada, name="escala_publicada"),
    path("painel/", views.painel, name="painel"),
    path("<int:sabado_id>/", views.escala_publicada, name="detalhe"),
    path("<int:sabado_id>/organizar/", views.organizar, name="organizar"),
    path("<int:sabado_id>/salvar/", views.salvar, name="salvar"),
    path("<int:sabado_id>/publicar/", views.publicar, name="publicar"),
    path("<int:sabado_id>/reabrir/", views.reabrir, name="reabrir"),
]
