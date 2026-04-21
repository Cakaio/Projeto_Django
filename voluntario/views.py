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
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.http import JsonResponse
from sabado.models import Sabado
import threading
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

        def _display(n):
            rem = n % 3
            return 3 if (rem == 0 and n > 0) else rem

        total_alt = Ocorrencia.objects.filter(advertido=user, tipo='ALERTA').count()
        total_adv = Ocorrencia.objects.filter(advertido=user, tipo='ADVERTENCIA').count()
        po_direto = Ocorrencia.objects.filter(advertido=user, regra__startswith='PO').exists()
        periodo_observacao = po_direto or total_adv >= 3

        context['saas_alertas']           = _display(total_alt)
        context['saas_alertas_max']       = 3
        context['saas_advertencias']      = _display(total_adv)
        context['saas_advertencias_max']  = 3
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
            total_alertas=Count('ocorrencias_recebidas', filter=Q(ocorrencias_recebidas__tipo='ALERTA')),
            total_advertencias=Count('ocorrencias_recebidas', filter=Q(ocorrencias_recebidas__tipo='ADVERTENCIA')),
            total_po_direto=Count('ocorrencias_recebidas', filter=Q(ocorrencias_recebidas__regra__startswith='PO')),
        )
        .order_by('first_name', 'last_name')
    )

    def _display(n):
        """Retorna n % 3, mas mantém 3 (e não 0) quando n é múltiplo de 3 positivo."""
        rem = n % 3
        return 3 if (rem == 0 and n > 0) else rem

    dados = []
    for v in voluntarios:
        alt = v.total_alertas
        adv = v.total_advertencias
        periodo_observacao = v.total_po_direto > 0 or adv >= 3
        dados.append({
            'voluntario': v,
            'alertas': _display(alt),
            'alertas_max': 3,
            'advertencias': _display(adv),
            'advertencias_max': 3,
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
    regra = request.POST.get("regra", "").strip()
    razao = request.POST.get("razao", "").strip() or None

    if not advertido_id or regra not in Ocorrencia.REGRAS_DICT:
        messages.error(request, "Dados inválidos.")
        return redirect("voluntario:saas")

    # Deriva o tipo a partir do prefixo da regra
    if regra.startswith("AL"):
        tipo = "ALERTA"
    elif regra.startswith("AD"):
        tipo = "ADVERTENCIA"
    else:  # PO
        tipo = "SUSPENSAO"

    advertido = get_object_or_404(Voluntario, pk=advertido_id)

    # Bloquear se já em Período de Observação
    ja_em_po = (
        Ocorrencia.objects.filter(advertido=advertido, regra__startswith='PO').exists()
        or Ocorrencia.objects.filter(advertido=advertido, tipo='ADVERTENCIA').count() >= 3
    )
    if ja_em_po:
        messages.error(request, f"{advertido.get_full_name() or advertido.username} está em Período de Observação e não pode receber novas ocorrências.")
        return redirect("voluntario:saas")

    Ocorrencia.objects.create(
        advertido=advertido,
        tipo=tipo,
        regra=regra,
        razao=razao,
        aplicado_por=request.user,
        automatico=False,
    )

    # Recontagem pós-criação
    total_alt = Ocorrencia.objects.filter(advertido=advertido, tipo='ALERTA').count()
    total_adv = Ocorrencia.objects.filter(advertido=advertido, tipo='ADVERTENCIA').count()
    po_direto = regra.startswith('PO')

    # Auto-gerar advertência se atingiu múltiplo de 3 alertas
    if tipo == 'ALERTA':
        adv_auto_esperadas = total_alt // 3
        adv_auto_existentes = Ocorrencia.objects.filter(advertido=advertido, tipo='ADVERTENCIA', automatico=True).count()
        if adv_auto_esperadas > adv_auto_existentes:
            Ocorrencia.objects.create(
                advertido=advertido,
                tipo='ADVERTENCIA',
                razao='Advertência automática por acúmulo de 3 alertas.',
                aplicado_por=request.user,
                automatico=True,
            )
            total_adv += 1
            threading.Thread(target=_enviar_email_ocorrencia, args=(advertido, 'ADVERTENCIA'), kwargs={'automatico': True}, daemon=True).start()

    # Email em background (não bloqueia a resposta)
    periodo_observacao = po_direto or total_adv >= 3
    if periodo_observacao:
        threading.Thread(target=_enviar_email_ocorrencia, args=(advertido, 'PERIODO_OBSERVACAO'), kwargs={'regra': regra}, daemon=True).start()
    elif tipo == 'ADVERTENCIA':
        threading.Thread(target=_enviar_email_ocorrencia, args=(advertido, 'ADVERTENCIA'), kwargs={'regra': regra}, daemon=True).start()
    elif tipo == 'ALERTA':
        threading.Thread(target=_enviar_email_ocorrencia, args=(advertido, 'ALERTA'), kwargs={'regra': regra}, daemon=True).start()

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
        'regra': o.regra or '',
        'regra_display': Ocorrencia.REGRAS_DICT.get(o.regra, '') if o.regra else '',
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
    total_alt = Ocorrencia.objects.filter(advertido=advertido, tipo='ALERTA').count()
    total_adv = Ocorrencia.objects.filter(advertido=advertido, tipo='ADVERTENCIA').count()
    po_direto = Ocorrencia.objects.filter(advertido=advertido, regra__startswith='PO').exists()
    periodo_observacao = po_direto or total_adv >= 3
    return JsonResponse({
        'ok': True,
        'alertas': total_alt % 3,
        'advertencias': total_adv if periodo_observacao else total_adv % 3,
        'periodo_observacao': periodo_observacao,
    })


EMAIL_TESTE_FALLBACK = 'viniciusgbasilio@gmail.com'

def _enviar_email_ocorrencia(advertido, tipo, automatico=False, regra=None):
    import logging
    from decouple import config as env_config
    logger = logging.getLogger(__name__)
    email_dest = advertido.email or getattr(advertido, 'email_alternativo', None) or EMAIL_TESTE_FALLBACK
    from_email = env_config('EMAIL_DISPARO_ADVERTENCIAS', default=settings.DEFAULT_FROM_EMAIL)

    from datetime import date
    MESES_PT = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
    hoje = date.today()
    mes_atual = f"{MESES_PT[hoje.month - 1]} de {hoje.year}"

    assunto = f'Notificação do SAAs — {mes_atual} — Projeto Criança Feliz'

    tipo_labels = {
        'ALERTA': 'Alerta',
        'ADVERTENCIA': 'Advertência' + (' (automática por acúmulo de 3 alertas)' if automatico else ''),
        'SUSPENSAO': 'Suspensão',
        'PERIODO_OBSERVACAO': 'Período de Observação',
    }

    if regra:
        descricao_regra = Ocorrencia.REGRAS_DICT.get(regra, regra)
        infracao_html = f"<li><b>{regra}:</b> {descricao_regra}</li>"
        infracao_txt  = f"  • {regra}: {descricao_regra}"
    else:
        infracao_html = f"<li>{tipo_labels.get(tipo, tipo)}</li>"
        infracao_txt  = f"  • {tipo_labels.get(tipo, tipo)}"

    nome = advertido.first_name or advertido.username

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#222;font-size:15px;line-height:1.7;">
  <p><b>Olá, {nome}!</b></p>
  <p>Esperamos que esteja bem.</p>
  <p>
    Gostaríamos de informar que, após acompanhamento das atividades do projeto,
    foi registrada a seguinte ocorrência relacionada à sua participação:
  </p>
  <p><b>Infração registrada:</b></p>
  <ul style="text-align:justify;padding-left:1.4em;">
    {infracao_html}
  </ul>
  <p>
    Lembramos que este e-mail não tem caráter punitivo, mas sim o propósito de promover
    o desenvolvimento individual e o alinhamento com os valores do projeto.
    Cada ocorrência representa uma chance de crescer e fortalecer o compromisso com o grupo.
  </p>
  <p>
    Sabemos do seu potencial e da sua importância para o projeto, e confiamos na sua
    capacidade de transformar esse feedback em crescimento. Estamos aqui para apoiar nesse processo.
  </p>
  <p>Qualquer dúvida ou necessidade de conversa, estamos à disposição.</p>
  <p>Atenciosamente,<br><b>Gestão de Talentos</b><br>Projeto Criança Feliz</p>
</div>
"""

    txt = (
        f"Boa tarde, {nome}!\n\n"
        "Esperamos que esteja bem.\n\n"
        "Gostaríamos de informar que, após acompanhamento das atividades do projeto,\n"
        "foi registrada a seguinte ocorrência relacionada à sua participação:\n\n"
        f"Infração registrada:\n{infracao_txt}\n\n"
        "Lembramos que este e-mail não tem caráter punitivo, mas sim o propósito de promover "
        "o desenvolvimento individual e o alinhamento com os valores do projeto.\n\n"
        "Sabemos do seu potencial e da sua importância para o projeto, e confiamos na sua "
        "capacidade de transformar esse feedback em crescimento. Estamos aqui para apoiar nesse processo.\n\n"
        "Qualquer dúvida ou necessidade de conversa, estamos à disposição.\n\n"
        "Atenciosamente,\nGestão de Talentos\nProjeto Criança Feliz"
    )

    try:
        msg = EmailMultiAlternatives(assunto, txt, from_email, [email_dest])
        msg.attach_alternative(html, 'text/html')
        msg.send(fail_silently=False)
        logger.info(f'[SAAs] Email enviado para {email_dest} — tipo={tipo}')
    except Exception as e:
        logger.error(f'[SAAs] Falha ao enviar email para {email_dest}: {e}')