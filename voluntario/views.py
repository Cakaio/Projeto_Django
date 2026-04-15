from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, TemplateView, UpdateView
from .models import Voluntario, PresencaVoluntario, Ocorrencia
from .forms import MeuPerfilForm
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.timezone import localdate
from django.contrib import messages
from django.db.models import Count, Q
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        total_adv = Ocorrencia.objects.filter(advertido=user, tipo='ADVERTENCIA').count()
        total_sus = Ocorrencia.objects.filter(advertido=user, tipo='SUSPENSAO').count()
        adv_restantes = total_adv % 3
        periodo_observacao = total_sus >= 3
        context['saas_advertencias'] = adv_restantes
        context['saas_advertencias_max'] = 3
        context['saas_suspensoes'] = total_sus if periodo_observacao else total_sus % 3
        context['saas_suspensoes_max'] = 3
        context['saas_periodo_observacao'] = periodo_observacao
        context['saas_ocorrencias'] = Ocorrencia.objects.filter(advertido=user).order_by('-criado_em')
        return context





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


AREAS_SAAS = {"GESTAO_DE_TALENTOS", "TRIADE"}


def _pode_ver_saas(user):
    return user.is_authenticated and (user.is_superuser or getattr(user, 'area', '') in AREAS_SAAS)


@login_required(login_url="/")
def saas_view(request):
    if not _pode_ver_saas(request.user):
        messages.error(request, "Você não tem permissão para acessar esta página.")
        return redirect("inicio")

    voluntarios = (
        Voluntario.objects
        .filter(is_active=True)
        .annotate(
            total_advertencias=Count('ocorrencias_recebidas', filter=Q(ocorrencias_recebidas__tipo='ADVERTENCIA')),
            total_suspensoes=Count('ocorrencias_recebidas', filter=Q(ocorrencias_recebidas__tipo='SUSPENSAO')),
        )
        .order_by('first_name', 'last_name')
    )

    dados = []
    for v in voluntarios:
        adv = v.total_advertencias
        sus = v.total_suspensoes  # já inclui suspensões automáticas gravadas no banco
        adv_restantes = adv % 3   # advertências desde a última suspensão gerada
        periodo_observacao = sus >= 3
        dados.append({
            'voluntario': v,
            'advertencias': adv_restantes,
            'advertencias_max': 3,
            'suspensoes': sus if periodo_observacao else sus % 3,
            'suspensoes_max': 3,
            'periodo_observacao': periodo_observacao,
        })

    context = {
        'dados': dados,
        'areas': LISTA_AREAS,
    }
    return render(request, "saas.html", context)


@login_required(login_url="/")
def criar_ocorrencia(request):
    if not _pode_ver_saas(request.user):
        messages.error(request, "Você não tem permissão para realizar esta ação.")
        return redirect("inicio")

    if request.method != "POST":
        return redirect("voluntario:saas")

    advertido_id = request.POST.get("advertido_id")
    tipo = request.POST.get("tipo")
    razao = request.POST.get("razao", "").strip() or None

    if not advertido_id or tipo not in ("ADVERTENCIA", "SUSPENSAO"):
        messages.error(request, "Dados inválidos.")
        return redirect("voluntario:saas")

    advertido = get_object_or_404(Voluntario, pk=advertido_id)

    # Bloquear se em Período de Observação (≥ 3 suspensões)
    total_sus_atual = Ocorrencia.objects.filter(advertido=advertido, tipo='SUSPENSAO').count()
    if total_sus_atual >= 3:
        messages.error(request, f"{advertido.get_full_name() or advertido.username} está em Período de Observação e não pode receber novas ocorrências.")
        return redirect("voluntario:saas")

    Ocorrencia.objects.create(
        advertido=advertido,
        tipo=tipo,
        razao=razao,
        aplicado_por=request.user,
        automatico=False,
    )

    # Recontagem pós-criação
    total_adv = Ocorrencia.objects.filter(advertido=advertido, tipo='ADVERTENCIA').count()
    total_sus = Ocorrencia.objects.filter(advertido=advertido, tipo='SUSPENSAO').count()

    # Auto-gerar suspensão se atingiu múltiplo de 3 advertências
    sus_auto_esperadas = total_adv // 3
    sus_auto_existentes = Ocorrencia.objects.filter(advertido=advertido, tipo='SUSPENSAO', automatico=True).count()

    if sus_auto_esperadas > sus_auto_existentes:
        Ocorrencia.objects.create(
            advertido=advertido,
            tipo='SUSPENSAO',
            razao='Suspensão automática por acúmulo de 3 advertências.',
            aplicado_por=request.user,
            automatico=True,
        )
        total_sus += 1
        _enviar_email_ocorrencia(advertido, 'SUSPENSAO', automatico=True)

    # Checar período de observação pós-registro
    if total_sus >= 3:
        _enviar_email_ocorrencia(advertido, 'PERIODO_OBSERVACAO')
    elif tipo == 'SUSPENSAO':
        _enviar_email_ocorrencia(advertido, 'SUSPENSAO')
    elif tipo == 'ADVERTENCIA':
        _enviar_email_ocorrencia(advertido, 'ADVERTENCIA')

    messages.success(request, f"{dict(Ocorrencia.TIPOS).get(tipo)} registrada para {advertido.get_full_name() or advertido.username}.")
    return redirect("voluntario:saas")


@login_required(login_url="/")
def historico_ocorrencias(request, pk):
    if not _pode_ver_saas(request.user):
        return JsonResponse({'error': 'Sem permissão'}, status=403)
    voluntario = get_object_or_404(Voluntario, pk=pk)
    ocorrencias = Ocorrencia.objects.filter(advertido=voluntario).order_by('-criado_em')
    data = [{
        'id': str(o.id),
        'tipo': o.tipo,
        'tipo_display': dict(Ocorrencia.TIPOS).get(o.tipo, o.tipo),
        'razao': o.razao or '',
        'automatico': o.automatico,
        'aplicado_por': (o.aplicado_por.get_full_name() or o.aplicado_por.username) if o.aplicado_por else '—',
        'criado_em': o.criado_em.strftime('%d/%m/%Y %H:%M'),
    } for o in ocorrencias]
    return JsonResponse({
        'ocorrencias': data,
        'nome': voluntario.get_full_name() or voluntario.username,
    })


@login_required(login_url="/")
def deletar_ocorrencia(request, ocorrencia_id):
    if not _pode_ver_saas(request.user):
        return JsonResponse({'error': 'Sem permissão'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Método inválido'}, status=405)
    ocorrencia = get_object_or_404(Ocorrencia, pk=ocorrencia_id)
    advertido = ocorrencia.advertido
    ocorrencia.delete()
    # Retorna os novos totais para o frontend atualizar sem reload
    total_adv = Ocorrencia.objects.filter(advertido=advertido, tipo='ADVERTENCIA').count()
    total_sus = Ocorrencia.objects.filter(advertido=advertido, tipo='SUSPENSAO').count()
    adv_restantes = total_adv % 3
    periodo_observacao = total_sus >= 3
    return JsonResponse({
        'ok': True,
        'advertencias': adv_restantes,
        'suspensoes': total_sus if periodo_observacao else total_sus % 3,
        'periodo_observacao': periodo_observacao,
    })


def _enviar_email_ocorrencia(advertido, tipo, automatico=False):
    email_dest = advertido.email or getattr(advertido, 'email_alternativo', None)
    if not email_dest:
        return

    assuntos = {
        'ADVERTENCIA': 'Você recebeu uma advertência — Projeto Criança Feliz',
        'SUSPENSAO': 'Você recebeu uma suspensão — Projeto Criança Feliz',
        'PERIODO_OBSERVACAO': 'Você está em Período de Observação — Projeto Criança Feliz',
    }
    corpos = {
        'ADVERTENCIA': (
            f"Olá, {advertido.first_name or advertido.username}!\n\n"
            "Você recebeu uma advertência no Projeto Criança Feliz.\n"
            "Caso tenha dúvidas, entre em contato com a Gestão de Talentos ou a Tríade.\n\n"
            "Projeto Criança Feliz"
        ),
        'SUSPENSAO': (
            f"Olá, {advertido.first_name or advertido.username}!\n\n"
            "Você recebeu uma suspensão no Projeto Criança Feliz"
            + (" (gerada automaticamente pelo acúmulo de advertências)" if automatico else "") + ".\n"
            "Caso tenha dúvidas, entre em contato com a Gestão de Talentos ou a Tríade.\n\n"
            "Projeto Criança Feliz"
        ),
        'PERIODO_OBSERVACAO': (
            f"Olá, {advertido.first_name or advertido.username}!\n\n"
            "Você está em Período de Observação no Projeto Criança Feliz.\n"
            "Isso ocorre após o acúmulo de suspensões. Entre em contato com a Gestão de Talentos ou a Tríade.\n\n"
            "Projeto Criança Feliz"
        ),
    }

    try:
        send_mail(
            subject=assuntos.get(tipo, 'Notificação — Projeto Criança Feliz'),
            message=corpos.get(tipo, ''),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email_dest],
            fail_silently=True,
        )
    except Exception:
        pass