from django.views.generic import ListView, DetailView, TemplateView
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.timezone import localdate
from django.contrib import messages
from .models import Atendido, PresencaAtendido
from sabado.models import Sabado
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required

LISTA_SALAS = [
    ("VIOLETA", "Violeta"),
    ("ANIL", "Anil"),
    ("AZUL", "Azul"),
    ("VERDE", "Verde"),
    ("AMARELO", "Amarelo"),
    ("LARANJA", "Laranja"),
    ("VERMELHO", "Vermelho"),
    ("FAMILIA_FELIZ", "Família Feliz"),
]

class ListaAtendido(LoginRequiredMixin, ListView):
    model = Atendido
    template_name = 'lista_atendidos.html'
    context_object_name = 'atendidos'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["salas"] = LISTA_SALAS
        return context


class DetalheAtendido(LoginRequiredMixin, DetailView):
    model = Atendido
    template_name = 'detalhe_atendido.html'

class AtendidoView(LoginRequiredMixin, TemplateView):
    template_name = "atendido_view.html"


# ✅ view protegida com login
@login_required(login_url="/")
def RegistrarPresencasAtendidos(request):
    hoje = localdate()
    AREAS_PERMITIDAS = [
        "VIOLETA", "ANIL", "AZUL", "VERDE", "AMARELO", "LARANJA", "VERMELHO", "FAMILIA_FELIZ", "ADM/FIN", "TRIADE"
    ]

    # Impede registro se usuário não tem área definida

    if not hasattr(request.user, 'area') or not request.user.area:
        messages.error(request, "❌ Você não pode registrar presença sem ter uma área definida no cadastro.")
        return redirect("inicio")
    if request.user.area not in AREAS_PERMITIDAS:
        messages.error(request, "❌ Você não pode registrar presença. Sua área não tem permissão para este registro.")
        return redirect("inicio")

    # Busca o sábado cadastrado para hoje (data exata)
    sabado_obj = Sabado.objects.filter(data=hoje).first()
    if not sabado_obj:
        messages.warning(request, "Não existe sábado cadastrado para hoje. O registro de presenças só é permitido no sábado cadastrado.")
        return render(request, "presencas_atendidos.html", {"atendidos": [], "salas": LISTA_SALAS, "sabado_data": None, "hoje": hoje})

    atendidos = Atendido.objects.filter(sala__in=AREAS_PERMITIDAS).exclude(
        presencas__data=sabado_obj
    ).order_by("nome")

    if request.method == "POST":
        registros_criados = 0
        for atendido in atendidos:
            presenca = request.POST.get(f"presenca_{atendido.id}")
            if presenca:
                PresencaAtendido.objects.create(
                    atendido=atendido,
                    presenca=presenca,
                    data=sabado_obj,
                    registrado_por=request.user
                )
                registros_criados += 1
        if registros_criados > 0:
            messages.success(request, f"✅ {registros_criados} presenças salvas com sucesso!")
        else:
            messages.warning(request, "⚠️ Nenhuma presença selecionada.")
        atendidos = Atendido.objects.filter(sala__in=AREAS_PERMITIDAS).exclude(
            presencas__data=sabado_obj
        ).order_by("nome")

    # Para debug: lista todos os sábados cadastrados
    sabados_cadastrados = Sabado.objects.all().order_by('data')
    contexto = {
        "atendidos": atendidos,
        "salas": LISTA_SALAS,
        "sabado_data": sabado_obj.data,
        "hoje": hoje,
        "sabados_cadastrados": sabados_cadastrados,
        "sabado_encontrado": sabado_obj is not None,
        "hoje_repr": repr(hoje),
    }
    return render(request, "presencas_atendidos.html", contexto)