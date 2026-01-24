from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.forms import modelformset_factory
from django.views.generic import ListView, DetailView, TemplateView
import json
from decimal import Decimal, InvalidOperation
from .models import LISTA_SALAS, Semanario, Atividade, Material
from .forms import SemanarioForm, AtividadeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.contrib import messages

def criar_semanario(request):
    AtividadeFormSet = modelformset_factory(Atividade, form=AtividadeForm, extra=5, can_delete=False)

    if request.method == "POST":
        semanario_form = SemanarioForm(request.POST)
        # for POST, garantir queryset vazio para receber apenas os forms enviados
        formset = AtividadeFormSet(request.POST, queryset=Atividade.objects.none())

        if semanario_form.is_valid() and formset.is_valid():
            semanario = semanario_form.save()
            sala = semanario.sala

            # salvando atividades e capturando a ordem para relacionar materiais posteriores
            saved_atividades = []
            for form in formset:
                atividade = form.save(commit=False)
                if atividade.atividade:
                    atividade.semanario = semanario
                    atividade.save()
                    saved_atividades.append(atividade)
                else:
                    saved_atividades.append(None)

            # processar materiais enviados como JSON no campo oculto 'materiais_json'
            materiais_json = request.POST.get('materiais_json', '')
            if materiais_json:
                try:
                    materiais_dict = json.loads(materiais_json)
                except Exception:
                    materiais_dict = {}

                # materiais_dict tem chaves como '0', '1', ... (índices do formset)
                for idx_str, mats in materiais_dict.items():
                    try:
                        idx = int(idx_str)
                    except ValueError:
                        continue
                    if idx < 0 or idx >= len(saved_atividades):
                        continue
                    atividade_obj = saved_atividades[idx]
                    if not atividade_obj:
                        continue
                    for m in mats:
                        nome = m.get('nome', '').strip()
                        quantidade = m.get('quantidade', '').strip()
                        unidade = m.get('unidade', '').strip()
                        if nome:
                            # validar quantidade, usando default 1 quando vazio ou inválido
                            if quantidade:
                                try:
                                    qtd = Decimal(quantidade)
                                except (InvalidOperation, TypeError):
                                    qtd = Decimal('1')
                            else:
                                qtd = Decimal('1')
                            Material.objects.create(atividade=atividade_obj, nome=nome, quantidade=qtd, unidade=(unidade or 'UN'))

            messages.success(request, "✅ Semanário, atividades e materiais salvos com sucesso!")
            return redirect("semanario:criar_semanario")
        else:
            # adicionar mensagens para facilitar diagnóstico em tela
            if semanario_form.errors:
                messages.error(request, f"Erro no Semanário: {semanario_form.errors}")
            if formset.non_form_errors():
                messages.error(request, f"Erros no formset: {formset.non_form_errors()}")
            for i, f in enumerate(formset.forms):
                if f.errors:
                    messages.error(request, f"Erro na Atividade #{i+1}: {f.errors}")

    else:
        semanario_form = SemanarioForm()
        formset = AtividadeFormSet(queryset=Atividade.objects.none())

    return render(request, "criar_semanario.html", {"semanario_form": semanario_form, "formset": formset})


# Salvar materiais via modal
def adicionar_material(request, atividade_id):
    if request.method == "POST":
        atividade = get_object_or_404(Atividade, id=atividade_id)
        nome = request.POST.get("nome")
        quantidade = request.POST.get("quantidade")
        unidade = request.POST.get("unidade")

        if nome:
            Material.objects.create(atividade=atividade, nome=nome, quantidade=quantidade, unidade=unidade)
            return JsonResponse({"success": True})
    return JsonResponse({"success": False})

class SemanarioView(LoginRequiredMixin, TemplateView):
    template_name = "semanario_view.html"

def editar_semanario(request, semanario_id):
    semanario = get_object_or_404(Semanario, id=semanario_id)
    AtividadeFormSet = modelformset_factory(Atividade, form=AtividadeForm, extra=0, can_delete=False)

    # Verificar permissão de edição com base na sala do usuário
    if request.user.area != semanario.sala:
        messages.error(request, "❌ Você não pode editar semanários de outra sala.")
        return redirect("semanario:lista_semanarios")

    # Pegando atividades existentes ou criando 5 vazias
    atividades_existentes = list(semanario.atividades.all())
    while len(atividades_existentes) < 5:
        atividades_existentes.append(None)  # placeholder para atividades novas

    if request.method == "POST":
        semanario_form = SemanarioForm(request.POST, instance=semanario)
        # passar a sala para que o campo 'competencia' renderize as opções corretas
        formset = AtividadeFormSet(request.POST, queryset=semanario.atividades.all(), form_kwargs={'sala': semanario.sala})

        if semanario_form.is_valid() and formset.is_valid():
            semanario = semanario_form.save()
            saved_atividades = []
            for form in formset:
                atividade = form.save(commit=False)
                if atividade.atividade:
                    atividade.semanario = semanario
                    atividade.save()
                    saved_atividades.append(atividade)
                else:
                    saved_atividades.append(None)

            # processar materiais via JSON
            materiais_json = request.POST.get('materiais_json', '')
            if materiais_json:
                try:
                    materiais_dict = json.loads(materiais_json)
                except Exception:
                    materiais_dict = {}

                for idx_str, mats in materiais_dict.items():
                    try:
                        idx = int(idx_str)
                        atividade_obj = saved_atividades[idx]
                        if not atividade_obj:
                            continue
                        for m in mats:
                            nome = m.get('nome', '').strip()
                            quantidade = m.get('quantidade', '').strip()
                            unidade = m.get('unidade', '').strip()
                            if nome:
                                if quantidade:
                                    try:
                                        qtd = Decimal(quantidade)
                                    except (InvalidOperation, TypeError):
                                        qtd = Decimal('1')
                                else:
                                    qtd = Decimal('1')
                                Material.objects.create(
                                    atividade=atividade_obj, nome=nome, quantidade=qtd, unidade=(unidade or 'UN')
                                )
                    except (ValueError, IndexError):
                        continue

            messages.success(request, "✅ Semanário atualizado com sucesso!")
            return redirect("semanario:lista_semanarios")
        else:
            # Diagnóstico detalhado dos erros do formset e do form principal
            with open('semanario_form_errors.log', 'a', encoding='utf-8') as log:
                log.write(f"\n--- Erros em {timezone.now()} ---\n")
                if semanario_form.errors:
                    log.write(f"Erros no SemanarioForm: {semanario_form.errors}\n")
                if formset.non_form_errors():
                    log.write(f"Non form errors do formset: {formset.non_form_errors()}\n")
                for i, f in enumerate(formset.forms):
                    if f.errors:
                        log.write(f"Erro na Atividade #{i+1}: {f.errors}\n")
                        messages.error(request, f"Erro na Atividade #{i+1}: {f.errors}")
            messages.error(request, "Existem erros no formulário. Confira os campos.")

    else:
        semanario_form = SemanarioForm(instance=semanario)
        # passar a sala para que o campo 'competencia' já venha preenchido ao carregar a página
        formset = AtividadeFormSet(queryset=semanario.atividades.all(), form_kwargs={'sala': semanario.sala})

    return render(request, "editar_semanario.html", {
        "semanario_form": semanario_form,
        "formset": formset,
        "semanario": semanario
    })

class SemanarioListView(LoginRequiredMixin, ListView):
    model = Semanario
    template_name = "lista_semanarios.html"
    context_object_name = "semanarios"

    def get_queryset(self):
        hoje = timezone.now().date()
        return Semanario.objects.filter(
            data__data__gt=hoje + timezone.timedelta(days=-14)
        ).order_by("data__data")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["salas"] = LISTA_SALAS
        context["hoje"] = timezone.now().date()
        
        # Criar um dicionário indicando quais salas têm semanários
        salas_com_semanarios = set()
        for semanario in context["semanarios"]:
            salas_com_semanarios.add(semanario.sala)
        context["salas_com_semanarios"] = salas_com_semanarios
        
        return context


def listar_materiais(request, atividade_id):
    materiais = Material.objects.filter(atividade_id=atividade_id)

    data = [
        {
            "id": m.id,
            "nome": m.nome,
            "quantidade": str(m.quantidade),
            "unidade": m.unidade,
        }
        for m in materiais
    ]

    return JsonResponse(data, safe=False)

def salvar_materiais(request):
    data = json.loads(request.body)
    atividade_id = data.get("atividade_id")
    materiais = data.get("materiais", [])

    Material.objects.filter(atividade_id=atividade_id).delete()

    for m in materiais:
        Material.objects.create(
            atividade_id=atividade_id,
            nome=m["nome"],
            quantidade=m["quantidade"],
            unidade=m["unidade"]
        )

    return JsonResponse({"success": True})


class VisualizarSemanario(LoginRequiredMixin, DetailView):
    model = Semanario
    template_name = "visualizar_semanario.html"
    context_object_name = "semanario"
    pk_url_kwarg = "semanario_id"