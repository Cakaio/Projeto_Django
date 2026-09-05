import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView
from voluntario.models import Voluntario

from .forms import AvisoForm
from .models import Aviso, InscricaoPush
from .services import enviar_push


def _corpo_json(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return {}


@login_required
@require_POST
def inscrever(request):
    """Grava a inscrição de push do aparelho.

    Chaveado por endpoint, não por voluntário: o navegador reemite o mesmo
    endpoint ao reinscrever, e num aparelho compartilhado a inscrição precisa
    passar para quem logou por último.
    """
    dados = _corpo_json(request)
    endpoint = dados.get("endpoint")
    chaves = dados.get("keys") or {}
    p256dh, auth = chaves.get("p256dh"), chaves.get("auth")

    if not (endpoint and p256dh and auth):
        return JsonResponse({"ok": False, "erro": "inscrição incompleta"}, status=400)

    InscricaoPush.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "voluntario": request.user,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
        },
    )
    return JsonResponse({"ok": True})


@login_required
@require_POST
def desinscrever(request):
    endpoint = _corpo_json(request).get("endpoint")
    if endpoint:
        # Filtrar pelo voluntário também: sem isso, um POST forjado apagaria
        # inscrição de outra pessoa.
        InscricaoPush.objects.filter(voluntario=request.user, endpoint=endpoint).delete()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def testar(request):
    """Dispara um push de teste para o próprio usuário.

    Síncrono de propósito: o voluntário está olhando para a tela esperando o
    resultado. É a ferramenta de diagnóstico do onboarding.
    """
    enviados = enviar_push(
        [request.user],
        "Funcionou! 🎉",
        "As notificações do PCF estão ativas neste aparelho.",
        url="/notificacoes/instalar/",
        tag="teste",
    )
    return JsonResponse({"ok": enviados > 0, "enviados": enviados})


# Mesmo padrão de restrição usado em sabado/views.py:236.
AREAS_QUE_PODEM_AVISAR = {"TRIADE", "GESTAO_DE_TALENTOS"}


def _publico_do_aviso(aviso):
    """Voluntários que vão receber. Sempre só os ativos.

    Voluntario.objects.ativos() filtra data_saida E is_active — filtrar só
    data_saida na mão deixaria passar login desativado.
    """
    ativos = Voluntario.objects.ativos()
    if aviso.destino == "AREA":
        return ativos.filter(area=aviso.alvo)
    return ativos


@login_required
def avisos(request):
    if request.user.area not in AREAS_QUE_PODEM_AVISAR and not request.user.is_superuser:
        raise PermissionDenied("Só a Tríade e a Gestão de Talentos enviam avisos.")

    if request.method == "POST":
        form = AvisoForm(request.POST)
        if form.is_valid():
            aviso = form.save(commit=False)
            aviso.autor = request.user
            aviso.save()

            # Síncrono de propósito: o gestor espera a contagem na tela, e o
            # público é de algumas dezenas de pessoas.
            aviso.total_enviado = enviar_push(
                _publico_do_aviso(aviso), aviso.titulo, aviso.mensagem, url="/inicio/"
            )
            aviso.save(update_fields=["total_enviado"])

            messages.success(
                request, f"Aviso enviado para {aviso.total_enviado} aparelho(s)."
            )
            return redirect("notificacoes:avisos")
    else:
        form = AvisoForm()

    return render(request, "notificacoes/avisos.html", {
        "form": form,
        "avisos": Aviso.objects.select_related("autor")[:20],
    })


class InstalarView(LoginRequiredMixin, TemplateView):
    """Onboarding de instalação da PWA.

    É a peça que decide se o projeto pega ou não: no iOS a instalação é manual
    e pouco óbvia, e sem estas instruções ninguém instala.
    """
    template_name = "notificacoes/instalar.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["vapid_public_key"] = settings.VAPID_PUBLIC_KEY
        contexto["push_disponivel"] = bool(settings.VAPID_PUBLIC_KEY)
        contexto["inscricoes"] = self.request.user.inscricoes_push.all()
        return contexto


class OfflineView(TemplateView):
    """Sem @login_required de propósito: é a tela mostrada quando não há rede.

    Se a sessão expirou E a rede caiu, uma página de offline atrás de login
    viraria redirect para um login que também não carrega.
    """
    template_name = "notificacoes/offline.html"
