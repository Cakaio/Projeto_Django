from django.urls import path

from . import views

app_name = "notificacoes"

urlpatterns = [
    path("instalar/", views.InstalarView.as_view(), name="instalar"),
    path("inscrever/", views.inscrever, name="inscrever"),
    path("desinscrever/", views.desinscrever, name="desinscrever"),
    path("testar/", views.testar, name="testar"),
    path("avisos/", views.avisos, name="avisos"),
    path("offline/", views.OfflineView.as_view(), name="offline"),
]
