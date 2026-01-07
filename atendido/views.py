from django.views.generic import ListView, DetailView, TemplateView
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib import messages
from .models import Atendido, PresencaAtendido
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
@login_required(login_url="/")  # redireciona para a página de login se não estiver autenticado
def registrar_presencas(request):
    hoje = timezone.now().date()
    atendidos = Atendido.objects.exclude(
        presencas__data=hoje
    ).order_by("nome")

    if request.method == "POST":
        registros_criados = 0

        for atendido in atendidos:
            presenca = request.POST.get(f"presenca_{atendido.id}")
            if presenca:
                PresencaAtendido.objects.create(
                    atendido=atendido,
                    presenca=presenca,
                    data=hoje
                )
                registros_criados += 1

        if registros_criados > 0:
            messages.success(request, f"✅ {registros_criados} presenças salvas com sucesso!")
        else:
            messages.warning(request, "⚠️ Nenhuma presença selecionada.")

        atendidos = Atendido.objects.exclude(
            presencas__data=hoje
        ).order_by("nome")

    contexto = {
        "atendidos": atendidos,
        "salas": LISTA_SALAS,
        "hoje": hoje,
    }
    return render(request, "presencas_atendidos.html", contexto)