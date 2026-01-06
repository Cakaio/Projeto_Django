from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, TemplateView
from .models import Voluntario, PresencaVoluntario
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages

# Create your views here.
class VoluntarioView(LoginRequiredMixin, TemplateView):
    template_name = "voluntario_view.html"

LISTA_AREAS = [
    ("VIOLETA", "Violeta"),
    ("ANIL", "Anil"),
    ("AZUL", "Azul"),
    ("VERDE", "Verde"),
    ("AMARELO", "Amarelo"),
    ("LARANJA", "Laranja"),
    ("VERMELHO", "Vermelho"),
    ("FAMILIA_FELIZ", "Família Feliz"),
    ("MARKETING", "Marketing"),
    ("ADM/FIN", "Adm/Fin"),
    ("CR/RE", "Cr/Re"),
    ("EVENTOS", "Eventos"),
    ("GESTAO_DE_TALENTOS", "Gestão de Talentos"),
    ("RECREACAO", "Recreação"),
    ("SUPPLY", "Supply"),
    ("PROJETOS", "Projetos"),
    ("TRIADE", "Tríade"),
]

class ListaVoluntario(LoginRequiredMixin, ListView):
    model = Voluntario
    template_name = 'lista_voluntarios.html'
    context_object_name = 'voluntarios'

    def get_queryset(self):
        # 🔹 Retorna apenas os voluntários ativos
        return Voluntario.objects.filter(is_active=True).order_by('first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["areas"] = LISTA_AREAS
        return context

# ✅ view protegida com login
@login_required(login_url="/")
def RegistrarPresencasVoluntarios(request):
    hoje = timezone.now().date()
    voluntarios = Voluntario.objects.exclude(
        presencas__data=hoje
    ).order_by("first_name")

    if request.method == "POST":
        registros_criados = 0

        for voluntario in voluntarios:
            presenca = request.POST.get(f"presenca_{voluntario.id}")
            if presenca:
                PresencaVoluntario.objects.create(
                    voluntario=voluntario,
                    presenca=presenca,
                    data=hoje
                )
                registros_criados += 1

        if registros_criados > 0:
            messages.success(request, f"✅ {registros_criados} presenças salvas com sucesso!")
        else:
            messages.warning(request, "⚠️ Nenhuma presença selecionada.")

        # Atualiza a lista
        voluntarios = Voluntario.objects.exclude(
            presencas__data=hoje
        ).order_by("first_name")

    contexto = {
        "voluntarios": voluntarios,
        "areas": LISTA_AREAS,
        "hoje": hoje,
    }
    return render(request, "presencas_voluntarios.html", contexto)