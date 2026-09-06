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
from .views import inicio, LandingView, busca, midia
from django.contrib.auth import views as auth_view
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),

    # O service worker TEM que ser servido na raiz: o escopo dele é limitado ao
    # próprio caminho, então em /static/ ele não controlaria o site e a PWA não
    # instalaria.
    path('sw.js', TemplateView.as_view(
        template_name='sw.js',
        # charset explicito: sem ele o navegador le o UTF-8 como latin-1
        # e os acentos dos comentarios viram mojibake.
        content_type='application/javascript; charset=utf-8',
    ), name='service_worker'),
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
    # /pautas/ é a rota canônica. O namespace legado mantém favoritos e links
    # antigos em /gerenciamento/ funcionando durante a transição.
    path('pautas/', include('gerenciamento.urls', namespace='gerenciamento')),
    path('gerenciamento/', include('gerenciamento.urls', namespace='gerenciamento_legacy')),
    path('parceiros/', include('parceiros.urls', namespace='parceiros')),
    path('editais/', include('editais.urls', namespace='editais')),
    path('projetos/', include('projetos.urls', namespace='projetos')),
    path('acervo/', include('acervo.urls', namespace='acervo')),
    path('estudio/', include('estudio.urls', namespace='estudio')),
    path('notificacoes/', include('notificacoes.urls', namespace='notificacoes')),
    # A revista entra na RAIZ de propósito: o prefixo 'revista/' já está escrito
    # em cada rota dela, porque a página do doador mora em '/r/<token>/' — link
    # curto, para colar em e-mail e WhatsApp. Dois include com o mesmo namespace
    # se sobrescreveriam no reverse, então é um include só, montado aqui.
    path('', include('revista.urls', namespace='revista')),
]

# O WhiteNoise entrega /static/, mas NÃO entrega /media/ — e /media/ são os
# uploads. Servir só com DEBUG=True deixaria as fotos em 404 na produção; e
# servir tudo aberto, como estava, publicava documento de criança e comprovante
# de reembolso para qualquer um. A view `midia` resolve os dois: entrega as
# fotos da revista sem login (a página do doador é pública por design) e exige
# sessão para o resto.
urlpatterns += [
    re_path(r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'), midia),
]
