from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, TemplateView, UpdateView
from .models import Voluntario, PresencaVoluntario
from .forms import MeuPerfilForm
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.timezone import localdate
from django.contrib import messages
from sabado.models import Sabado

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
    ("ADM/FIN", "ADM/FIN"),
    ("CR/RE", "CR/RE"),
    ("EVENTOS", "Eventos"),
    ("GESTAO_DE_TALENTOS", "Gestão de Talentos"),
    ("RECREACAO", "Recreação"),
    ("SUPPLY", "Supply"),
    ("PROJETOS", "Projatos"),
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
    hoje = localdate()
    AREAS_PERMITIDAS = ["TRIADE", "GESTAO_DE_TALENTOS"]

    # Impede registro se usuário não tem área definida ou não está em áreas permitidas
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
        return render(request, "presencas_voluntarios.html", {"voluntarios": [], "areas": LISTA_AREAS, "hoje": hoje})

    voluntarios = Voluntario.objects.filter(is_active=True).exclude(
        presencas__data=sabado_obj
    ).order_by("first_name")

    if request.method == "POST":
        registros_criados = 0
        for voluntario in voluntarios:
            presenca = request.POST.get(f"presenca_{voluntario.id}")
            if presenca:
                PresencaVoluntario.objects.create(
                    voluntario=voluntario,
                    presenca=presenca,
                    data=sabado_obj,
                    registrado_por=request.user
                )
                registros_criados += 1
        if registros_criados > 0:
            messages.success(request, f"✅ {registros_criados} presenças salvas com sucesso!")
        else:
            messages.warning(request, "⚠️ Nenhuma presença selecionada.")
        voluntarios = Voluntario.objects.filter(is_active=True).exclude(
            presencas__data=sabado_obj
        ).order_by("first_name")

    contexto = {
        "voluntarios": voluntarios,
        "areas": LISTA_AREAS,
        "hoje": hoje,
    }
    return render(request, "presencas_voluntarios.html", contexto)



class MeuPerfilView(LoginRequiredMixin, UpdateView):
    model = Voluntario
    form_class = MeuPerfilForm
    template_name = "meu_perfil.html"
    success_url = reverse_lazy("voluntario:meu_perfil")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "✅ Perfil atualizado com sucesso!")
        return super().form_valid(form)
