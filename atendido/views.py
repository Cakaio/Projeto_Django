from django.views.generic import ListView, DetailView, TemplateView
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.timezone import localdate
from django.contrib import messages
from .models import Atendido, PresencaAtendido
from sabado.models import Sabado
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from .models import Atendido, PresencaAtendido, ResponsavelAtendido, Familia, Mudanca
from .forms import (
    AtendidoForm, FamiliaForm, AtendidoInclusivoForm, ResponsavelFormSet,
)
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


# 6 categorias fixas de impacto, com os aspectos agrupados (ajuda ao operador)
CATEGORIAS_IMPACTO = [
    ("Desenvolvimento Socioemocional",
     "Mais alegre; deixou de ser chorona; melhora na timidez; está mais comunicativa; compreensão de si mesmo e do outro; apoio emocional."),
    ("Relacionamento e Socialização",
     "Socialização; melhor convívio com outras crianças; melhora na convivência; mais comunicação."),
    ("Desenvolvimento Cognitivo e Escolar",
     "Aprendizagem; melhor desempenho na escola; desenvolvimento da atenção."),
    ("Autonomia e Responsabilidade",
     "Melhorou o comprometimento e a responsabilidade do atendido."),
    ("Desenvolvimento Integral da Criança",
     "Apoio no desenvolvimento da criança; desenvolvimento do atendido (crescimento geral)."),
    ("Apoio às Famílias",
     "Orientações educativas; segurança para os pais durante o período das atividades."),
]


def _pode_matricular(user):
    return user.is_superuser or getattr(user, 'is_matricula', False)


def _categorias_impacto(selecionados_ids):
    """Lista ordenada das 6 categorias com id, nome, aspectos e se está marcada."""
    por_nome = {m.mudanca: m for m in Mudanca.objects.filter(mudanca__in=[n for n, _ in CATEGORIAS_IMPACTO])}
    itens = []
    for nome, aspectos in CATEGORIAS_IMPACTO:
        m = por_nome.get(nome)
        if m:
            itens.append({'id': m.id, 'nome': nome, 'aspectos': aspectos, 'marcado': m.id in selecionados_ids})
    return itens


@login_required(login_url="/")
def buscar_responsaveis(request):
    if not _pode_matricular(request.user):
        return JsonResponse({'results': []})
    q = request.GET.get('q', '').strip()
    results = []
    if len(q) >= 2:
        qs = (
            ResponsavelAtendido.objects
            .filter(Q(nome__icontains=q) | Q(cpf__icontains=q))
            .order_by('nome')[:10]
        )
        results = [{
            'id': r.id,
            'nome': r.nome or '(sem nome)',
            'cpf': r.cpf or '',
            'parentesco': r.get_parentesco_display() if r.parentesco else '',
            'contato': r.contato or '',
        } for r in qs]
    return JsonResponse({'results': results})


@login_required(login_url="/")
def buscar_familias(request):
    if not _pode_matricular(request.user):
        return JsonResponse({'results': []})
    q = request.GET.get('q', '').strip()
    results = []
    if len(q) >= 2:
        qs = (
            Atendido.objects
            .filter(nome__icontains=q, familia__isnull=False)
            .select_related('familia')[:10]
        )
        vistos = set()
        for a in qs:
            fam = a.familia
            if fam.id in vistos:
                continue
            vistos.add(fam.id)
            desc = ' · '.join(filter(None, [
                fam.get_bairro_display() if fam.bairro else '',
                fam.get_cidade_display() if fam.cidade else '',
            ])) or 'família cadastrada'
            results.append({'atendido': a.nome, 'familia_id': fam.id, 'descricao': desc})
    return JsonResponse({'results': results})


@login_required(login_url="/")
def matricula_atendido(request, pk=None):
    """Matrícula/edição de atendido: criança + família + responsáveis + inclusão."""
    if not _pode_matricular(request.user):
        messages.error(request, "Você não tem permissão para matricular atendidos.")
        return redirect('atendido:atendido_view')

    atendido = get_object_or_404(Atendido, pk=pk) if pk else None
    familia_instance = atendido.familia if atendido else None
    inclusivo_instance = getattr(atendido, 'inclusivo', None) if atendido else None
    modo = 'editar' if atendido else 'criar'

    # Responsáveis existentes são tratados via chips; o formset é só para NOVOS.
    resp_qs = ResponsavelAtendido.objects.none()

    if request.method == 'POST':
        aform = AtendidoForm(request.POST, request.FILES, instance=atendido, prefix='at')
        fform = FamiliaForm(request.POST, instance=familia_instance, prefix='fam')
        rformset = ResponsavelFormSet(request.POST, prefix='resp', queryset=resp_qs)
        iform = AtendidoInclusivoForm(request.POST, instance=inclusivo_instance, prefix='inc')

        familia_existente_id = (request.POST.get('familia_existente') or '').strip()
        if not familia_existente_id.isdigit():
            familia_existente_id = ''
        usar_familia_existente = bool(familia_existente_id) and modo == 'criar'
        resp_existente_ids = [i for i in request.POST.getlist('resp_existente') if i and i.isdigit()]

        a_ok = aform.is_valid()
        r_ok = rformset.is_valid()
        i_ok = iform.is_valid()
        if usar_familia_existente:
            f_ok = Familia.objects.filter(pk=familia_existente_id).exists()
        else:
            f_ok = fform.is_valid()

        novos_validos = [
            form for form in rformset
            if getattr(form, 'cleaned_data', None)
            and not form.cleaned_data.get('DELETE')
            and form.cleaned_data.get('nome')
        ] if r_ok else []
        total_resp = len(resp_existente_ids) + len(novos_validos)

        if a_ok and f_ok and r_ok and i_ok and total_resp > 0:
            with transaction.atomic():
                if usar_familia_existente:
                    familia = Familia.objects.get(pk=familia_existente_id)
                else:
                    familia = fform.save()

                responsaveis = list(ResponsavelAtendido.objects.filter(pk__in=resp_existente_ids))
                for form in novos_validos:
                    cpf = form.cleaned_data.get('cpf')
                    if cpf:
                        existente = ResponsavelAtendido.objects.filter(cpf=cpf).first()
                        if existente:
                            responsaveis.append(existente)
                            continue
                    responsaveis.append(form.save())

                atendido_obj = aform.save(commit=False)
                atendido_obj.familia = familia
                if modo == 'criar':
                    atendido_obj.registrado_por = request.user
                atendido_obj.save()
                atendido_obj.responsavel.set(responsaveis)
                aform.save_m2m()  # aspectos_mudancas

                if atendido_obj.comissao_inclusiva:
                    inclusivo = iform.save(commit=False)
                    inclusivo.atendido = atendido_obj
                    inclusivo.save()

            messages.success(request, 'Matrícula salva com sucesso!')
            return redirect('atendido:detalhe_atendido', pk=atendido_obj.pk)
        else:
            if total_resp == 0:
                messages.error(request, 'Adicione ou vincule pelo menos um responsável.')
            else:
                messages.error(request, 'Confira os campos destacados e tente novamente.')
            selecionados = set(int(i) for i in request.POST.getlist('at-aspectos_mudancas') if i.isdigit())
            responsaveis_vinculados = list(ResponsavelAtendido.objects.filter(pk__in=resp_existente_ids))
    else:
        aform = AtendidoForm(instance=atendido, prefix='at')
        fform = FamiliaForm(instance=familia_instance, prefix='fam')
        rformset = ResponsavelFormSet(prefix='resp', queryset=resp_qs)
        iform = AtendidoInclusivoForm(instance=inclusivo_instance, prefix='inc')
        selecionados = set(atendido.aspectos_mudancas.values_list('id', flat=True)) if atendido else set()
        responsaveis_vinculados = list(atendido.responsavel.all()) if atendido else []
        familia_existente_id = ''
        usar_familia_existente = False

    return render(request, 'matricula_atendido.html', {
        'aform': aform,
        'fform': fform,
        'rformset': rformset,
        'iform': iform,
        'modo': modo,
        'atendido': atendido,
        'categorias_impacto': _categorias_impacto(selecionados),
        'responsaveis_vinculados': responsaveis_vinculados,
        'familia_existente_id': familia_existente_id,
        'usar_familia_existente': usar_familia_existente,
    })


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