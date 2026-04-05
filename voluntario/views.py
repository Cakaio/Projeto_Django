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
from django.shortcuts import render
from .models import Voluntario, PresencaVoluntario
from sabado.models import Sabado
import json

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





def visualizar_presencas_voluntarios(request):
    area = request.GET.get("area", "TODAS")
    sabados_ids = request.GET.getlist("sabados")

    sabados_disponiveis = Sabado.objects.order_by("-data")

    if sabados_ids:
        sabados = list(
            Sabado.objects.filter(id__in=sabados_ids).order_by("data")
        )
        sabados_selecionados = [int(i) for i in sabados_ids]
    else:
        sabados = list(Sabado.objects.order_by("-data")[:4])
        sabados.reverse()
        sabados_selecionados = [s.id for s in sabados]

    voluntarios = Voluntario.objects.all().order_by("username")

    if area != "TODAS":
        voluntarios = voluntarios.filter(area=area)

    voluntarios = list(voluntarios)

    areas_disponiveis = (
        Voluntario.objects.exclude(area__isnull=True)
        .exclude(area__exact="")
        .values_list("area", flat=True)
        .distinct()
        .order_by("area")
    )

    presencas = PresencaVoluntario.objects.filter(
        voluntario__in=voluntarios,
        data__in=sabados
    ).select_related("voluntario", "data")

    presencas_map = {
        (p.voluntario_id, p.data_id): p.presenca
        for p in presencas
    }

    dados_tabela = []

    total_presentes = 0
    total_ausentes = 0
    total_justificadas = 0
    total_registros = 0

    grafico_labels = []
    grafico_presentes = []

    for sabado in sabados:
        presentes_no_sabado = 0

        for voluntario in voluntarios:
            status = presencas_map.get((voluntario.id, sabado.id))
            if status == "PRESENTE":
                presentes_no_sabado += 1

        grafico_labels.append(sabado.data.strftime("%d/%m/%Y"))
        grafico_presentes.append(presentes_no_sabado)

    for voluntario in voluntarios:
        linha_presencas = []
        total_considerado = 0
        presentes_voluntario = 0

        for sabado in sabados:
            status = presencas_map.get((voluntario.id, sabado.id), None)

            linha_presencas.append({
                "sabado_id": sabado.id,
                "status": status,
            })

            if status:
                total_registros += 1
                total_considerado += 1

                if status == "PRESENTE":
                    total_presentes += 1
                    presentes_voluntario += 1
                elif status == "AUSENTE":
                    total_ausentes += 1
                elif status == "JUSTIFICADA":
                    total_justificadas += 1

        percentual = 0
        if total_considerado > 0:
            percentual = round((presentes_voluntario / total_considerado) * 100, 1)

        dados_tabela.append({
            "voluntario": voluntario,
            "area": getattr(voluntario, "area", ""),
            "presencas": linha_presencas,
            "percentual": percentual,
        })

    percentual_geral = 0
    if total_registros > 0:
        percentual_geral = round((total_presentes / total_registros) * 100, 1)

    context = {
        "area_atual": area,
        "areas_disponiveis": areas_disponiveis,
        "sabados_disponiveis": sabados_disponiveis,
        "sabados_selecionados": sabados_selecionados,
        "sabados": sabados,
        "dados_tabela": dados_tabela,
        "total_voluntarios": len(voluntarios),
        "total_sabados": len(sabados),
        "total_presentes": total_presentes,
        "total_ausentes": total_ausentes,
        "total_justificadas": total_justificadas,
        "percentual_geral": percentual_geral,
        "grafico_labels_json": json.dumps(grafico_labels),
        "grafico_presentes_json": json.dumps(grafico_presentes),
    }

    return render(request, "visualizar_presencas_voluntarios.html", context)