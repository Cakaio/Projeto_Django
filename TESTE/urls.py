"""
URL configuration for TESTE project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve
from .views import inicio, LandingView, busca
from django.contrib.auth import views as auth_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', LandingView.as_view(), name='landing'),
    path('buscar/', busca, name='busca'),
    path('login/', auth_view.LoginView.as_view(template_name='login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', auth_view.LogoutView.as_view(next_page='login'), name='logout'),
    path('inicio/', inicio.as_view(), name='inicio'),
    path('atendido/', include('atendido.urls', namespace='atendido')),
    path('voluntario/', include('voluntario.urls', namespace='voluntario')),
    path('semanario/', include('semanario.urls', namespace='semanario')),
    path('sabado/', include('sabado.urls', namespace='sabado')),
    path('supply/', include('supply.urls', namespace='supply')),
    path('adm/', include('adm.urls', namespace='adm')),
    path('forms/', include('forms_pcf.urls', namespace='forms_pcf')),
    path('ronda/', include('ronda.urls', namespace='ronda')),
    path('gerenciamento/', include('gerenciamento.urls', namespace='gerenciamento')),
    path('parceiros/', include('parceiros.urls', namespace='parceiros')),
]

# Arquivos estáticos e de mídia.
# ATENÇÃO: o helper `static()` do Django só funciona com DEBUG=True. Como o
# DEBUG agora vem do .env (e o padrão é False), usar só ele deixaria o site
# inteiro sem CSS, JS e imagens em produção. As rotas abaixo servem os arquivos
# independentemente do DEBUG, garantindo que nada quebre.
#
# O ideal, em produção, é o servidor web entregar esses arquivos: na aba "Web"
# do PythonAnywhere, mapeie  /static/ -> /home/pcf/Projeto_Django/static  e
# /media/ -> /home/pcf/Projeto_Django/media. Feito isso, o mapeamento tem
# precedência e estas rotas ficam apenas como reserva.
urlpatterns += [
    re_path(r'^%s(?P<path>.*)$' % settings.STATIC_URL.lstrip('/'),
            serve, {'document_root': settings.STATIC_ROOT}),
    re_path(r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'),
            serve, {'document_root': settings.MEDIA_ROOT}),
]
