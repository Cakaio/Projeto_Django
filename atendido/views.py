from django.views.generic import ListView, DetailView, TemplateView
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.timezone import localdate
from django.contrib import messages
from .models import Atendido, PresencaAtendido
from sabado.models import Sabado
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Atendido, PresencaAtendido
from sabado.models import Sabado
import json

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

    def get_queryset(self):
        return (
            Atendido.objects
            .filter(sala__in=[c for c, _ in LISTA_SALAS])
            .prefetch_related('responsavel')
            .order_by('sala', 'nome')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        atendidos = context['atendidos']

        # Pré-agrupa por sala para evitar O(n²) no template
        salas_map = {codigo: [] for codigo, _ in LISTA_SALAS}
        for a in atendidos:
            if a.sala in salas_map:
                salas_map[a.sala].append(a)

        context['salas_com_atendidos'] = [
            {'codigo': codigo, 'nome': nome, 'atendidos': salas_map[codigo]}
            for codigo, nome in LISTA_SALAS
        ]
        context['total_atendidos'] = atendidos.count()
        return context


class DetalheAtendido(LoginRequiredMixin, DetailView):
    model = Atendido
    template_name = 'detalhe_atendido.html'

class AtendidoView(LoginRequiredMixin, TemplateView):
    template_name = "atendido_view.html"


@login_required(login_url="/")
def RegistrarPresencasAtendidos(request):
    hoje = localdate()
    AREAS_PERMITIDAS = [
        "VIOLETA", "ANIL", "AZUL", "VERDE", "AMARELO", "LARANJA", "VERMELHO", "FAMILIA_FELIZ", "ADM/FIN", "TRIADE"
    ]

    if not hasattr(request.user, 'area') or not request.user.area:
        messages.error(request, "Você não pode registrar presença sem ter uma área definida no cadastro.")
        return redirect("inicio")
    if request.user.area not in AREAS_PERMITIDAS:
        messages.error(request, "Você não pode registrar presença. Sua área não tem permissão para este registro.")
        return redirect("inicio")

    sabado_obj = Sabado.objects.filter(data=hoje).first()
    if not sabado_obj:
        return render(request, "presencas_atendidos.html", {"atendidos": [], "salas": LISTA_SALAS, "sabado_data": None, "hoje": hoje})

    # Todos os atendidos ainda sem registro neste sábado
    atendidos = Atendido.objects.filter(sala__in=[c for c, _ in LISTA_SALAS]).exclude(
        presencas__data=sabado_obj
    ).order_by("sala", "nome")

    if request.method == "POST":
        registros_criados = 0
        for atendido in Atendido.objects.filter(sala__in=[c for c, _ in LISTA_SALAS]).exclude(presencas__data=sabado_obj):
            presenca = request.POST.get(f"presenca_{atendido.id}")
            if presenca in ("PRESENTE", "AUSENTE", "JUSTIFICADA"):
                PresencaAtendido.objects.create(
                    atendido=atendido,
                    presenca=presenca,
                    data=sabado_obj,
                    registrado_por=request.user,
                )
                registros_criados += 1
        if registros_criados:
            messages.success(request, f"{registros_criados} presenças salvas com sucesso!")
        else:
            messages.warning(request, "Nenhuma presença selecionada.")
        return redirect(request.path)

    # Agrupa atendidos por sala para o template
    atendidos_list = list(atendidos)
    salas_com_atendidos = []
    for codigo, nome in LISTA_SALAS:
        grupo = [a for a in atendidos_list if a.sala == codigo]
        if grupo:
            salas_com_atendidos.append({"codigo": codigo, "nome": nome, "atendidos": grupo})

    contexto = {
        "atendidos": atendidos_list,
        "salas_com_atendidos": salas_com_atendidos,
        "sabado_data": sabado_obj.data,
        "hoje": hoje,
    }
    return render(request, "presencas_atendidos.html", contexto)


def visualizar_presencas_atendidos(request):
    sala = request.GET.get("sala", "TODAS")
    sabados_ids = request.GET.getlist("sabados")

    sabados_disponiveis = Sabado.objects.order_by("-data")

    if sabados_ids:
        sabados = list(
            Sabado.objects.filter(id__in=sabados_ids).order_by("data")
        )
        sabados_selecionados = [int(i) for i in sabados_ids]
    else:
        sabados = list(Sabado.objects.order_by("-data")[:4])
        sabados.reverse()  # mais antigo -> mais recente
        sabados_selecionados = [s.id for s in sabados]

    atendidos = Atendido.objects.all().order_by("nome")

    if sala != "TODAS":
        atendidos = atendidos.filter(sala=sala)

    atendidos = list(atendidos)

    # Salas disponíveis para o filtro
    salas_disponiveis = (
        Atendido.objects.exclude(sala__isnull=True)
        .exclude(sala__exact="")
        .values_list("sala", flat=True)
        .distinct()
        .order_by("sala")
    )

    # Busca todas as presenças necessárias de uma vez
    presencas = PresencaAtendido.objects.filter(
        atendido__in=atendidos,
        data__in=sabados
    ).select_related("atendido", "data")

    presencas_map = {
        (p.atendido_id, p.data_id): p.presenca
        for p in presencas
    }

    dados_tabela = []

    total_presentes = 0
    total_ausentes = 0
    total_justificadas = 0
    total_registros = 0

    grafico_labels = []
    grafico_presentes = []

    # Dados do gráfico
    for sabado in sabados:
        presentes_no_sabado = 0
        for atendido in atendidos:
            status = presencas_map.get((atendido.id, sabado.id))
            if status == "PRESENTE":
                presentes_no_sabado += 1

        grafico_labels.append(sabado.data.strftime("%d/%m/%Y"))
        grafico_presentes.append(presentes_no_sabado)

    # Dados da tabela
    for atendido in atendidos:
        linha_presencas = []
        total_considerado = 0
        presentes_atendido = 0

        for sabado in sabados:
            status = presencas_map.get((atendido.id, sabado.id), None)

            linha_presencas.append({
                "sabado_id": sabado.id,
                "status": status,
            })

            if status:
                total_registros += 1
                total_considerado += 1

                if status == "PRESENTE":
                    total_presentes += 1
                    presentes_atendido += 1
                elif status == "AUSENTE":
                    total_ausentes += 1
                elif status == "JUSTIFICADA":
                    total_justificadas += 1

        percentual = 0
        if total_considerado > 0:
            percentual = round((presentes_atendido / total_considerado) * 100, 1)

        dados_tabela.append({
            "atendido": atendido,
            "sala": atendido.sala,
            "presencas": linha_presencas,
            "percentual": percentual,
        })

    percentual_geral = 0
    if total_registros > 0:
        percentual_geral = round((total_presentes / total_registros) * 100, 1)

    context = {
        "sala_atual": sala,
        "salas_disponiveis": salas_disponiveis,
        "sabados_disponiveis": sabados_disponiveis,
        "sabados_selecionados": sabados_selecionados,
        "sabados": sabados,
        "dados_tabela": dados_tabela,
        "total_atendidos": len(atendidos),
        "total_sabados": len(sabados),
        "total_presentes": total_presentes,
        "total_ausentes": total_ausentes,
        "total_justificadas": total_justificadas,
        "percentual_geral": percentual_geral,
        "grafico_labels_json": json.dumps(grafico_labels),
        "grafico_presentes_json": json.dumps(grafico_presentes),
    }

    return render(request, "visualizar_presencas.html", context)