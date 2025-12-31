from django.views.generic import ListView, DetailView
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib import messages
from .models import Atendido, PresencaAtendido

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

class Homepage(ListView):
    model = Atendido
    template_name = 'homepage.html'
    context_object_name = 'atendidos'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["salas"] = LISTA_SALAS
        return context


class DetalheAtendido(DetailView):
    model = Atendido
    template_name = 'detalhe_atendido.html'


def registrar_presencas(request):
    hoje = timezone.now().date()
    atendidos = Atendido.objects.exclude(
        presencas__data=hoje
    ).order_by("nome")

    if request.method == "POST":
        registros_criados = 0  # contador opcional

        for atendido in atendidos:
            presenca = request.POST.get(f"presenca_{atendido.id}")
            if presenca:  # só salva se o select tiver valor
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

        # Atualiza a lista (remove quem já foi marcado hoje)
        atendidos = Atendido.objects.exclude(
            presencas__data=hoje
        ).order_by("nome")

    contexto = {
        "atendidos": atendidos,
        "salas": LISTA_SALAS,
        "hoje": hoje,
    }
    return render(request, "presencas.html", contexto)