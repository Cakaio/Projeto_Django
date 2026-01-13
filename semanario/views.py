from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.forms import modelformset_factory
from django.views.generic import ListView, DetailView, TemplateView
import json
from decimal import Decimal, InvalidOperation
from .models import Semanario, Atividade, Material
from .forms import SemanarioForm, AtividadeForm
from django.contrib.auth.mixins import LoginRequiredMixin

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
