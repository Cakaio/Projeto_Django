from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import modelformset_factory
from .forms import MeuPedidoForm
from supply.forms import PedidoFormSet
from .models import Item, Movimentacao, Pedido
from django.shortcuts import render, redirect
from django.db.models import Prefetch
from semanario.models import Material
from sabado.models import Sabado
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Count, Q, Value, DecimalField
from django.db.models.functions import Coalesce
from sabado.models import Sabado
from semanario.models import Material , LISTA_SALAS, PEDIDO, TIPO_LOCAL # ajuste se o app/material estiver em outro app
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from voluntario.models import Voluntario, LISTA_AREAS



class ListaItensView(LoginRequiredMixin, ListView):
    model = Item
    template_name = 'supply/lista_itens.html'
    context_object_name = 'itens'

    def get_queryset(self):
        return Item.objects.filter(ativo=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['itens_estoque_baixo'] = [
            item for item in context['itens'] if item.estoque_baixo
        ]
        return context


class ListaMovimentacoesView(LoginRequiredMixin, ListView):
    model = Movimentacao
    template_name = 'supply/lista_movimentacoes.html'
    context_object_name = 'movimentacoes'
    paginate_by = 50

    def get_queryset(self):
        return Movimentacao.objects.select_related('item', 'registrado_por', 'sabado')


def painel_materiais(request):
    if request.user.area not in ["SUPPLY","TRIADE",]:
        messages.error(request, "Você não tem permissão para acessar esta página.")
        return redirect("/supply/")
    
    sabado_id = request.GET.get("sabado")
    tipo_local = request.GET.get("tipo_local")
    tipo_painel = request.GET.get("painel", "material")

    sabados = Sabado.objects.order_by("-data")[:40]

    if sabado_id:
        sabado = get_object_or_404(Sabado, pk=sabado_id)
    else:
        sabado = Sabado.objects.order_by("-data").first()

    if sabado is None:
        return render(request, "painel_materiais.html", {
            "sabados": sabados,
            "sabado": None,
            "tipo_painel": tipo_painel,
            "tipo_local_opcoes": TIPO_LOCAL,
            "total_itens": 0,
            "total_valor": Decimal("0.00"),
            "salas_map": [],
            "pedidos_map": [],
        })

    if tipo_painel == "pedido":
        qs = (
            Pedido.objects
            .select_related("requisitado_por", "sabado")
            .filter(sabado=sabado)
            .order_by("area", "nome")
        )

        if tipo_local:
            qs = qs.filter(tipo_local=tipo_local)

        total_itens = qs.count()
        total_valor = qs.aggregate(
            total=Coalesce(
                Sum("valor"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )["total"] or Decimal("0.00")

        nomes_areas = dict(LISTA_AREAS)
        pedidos_map = OrderedDict()

        for pedido in qs:
            area_key = pedido.area or "SEM_AREA"
            area_nome = nomes_areas.get(area_key, area_key if area_key != "SEM_AREA" else "Sem área")

            if area_key not in pedidos_map:
                pedidos_map[area_key] = {
                    "key": area_key,
                    "nome": area_nome,
                    "pedidos": [],
                    "total_itens": 0,
                    "total_valor": Decimal("0.00"),
                }

            pedidos_map[area_key]["pedidos"].append(pedido)
            pedidos_map[area_key]["total_itens"] += 1
            pedidos_map[area_key]["total_valor"] += pedido.valor or Decimal("0.00")

        return render(request, "painel_materiais.html", {
            "sabados": sabados,
            "sabado": sabado,
            "tipo_local": tipo_local,
            "tipo_painel": tipo_painel,
            "tipo_local_opcoes": TIPO_LOCAL,
            "total_itens": total_itens,
            "total_valor": total_valor,
            "salas_map": [],
            "pedidos_map": list(pedidos_map.values()),
        })

    qs = (
        Material.objects
        .select_related("atividade__semanario", "atividade__semanario__data")
        .filter(atividade__semanario__data=sabado)
        # Supply = destino explícito "SUPPLY" OU sem destino definido (nulo/vazio)
        .filter(Q(pedido="SUPPLY") | Q(pedido__isnull=True) | Q(pedido=""))
        .order_by("atividade__semanario__sala", "nome")
    )

    if tipo_local:
        qs = qs.filter(tipo_local=tipo_local)

    total_itens = qs.count()
    total_valor = qs.aggregate(
        total=Coalesce(
            Sum("valor"),
            Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
        )
    )["total"] or Decimal("0.00")

    nomes_salas = dict(LISTA_SALAS)
    salas_map = OrderedDict()

    for material in qs:
        sala_key = material.atividade.semanario.sala
        sala_nome = nomes_salas.get(sala_key, sala_key)

        if sala_key not in salas_map:
            salas_map[sala_key] = {
                "key": sala_key,
                "nome": sala_nome,
                "materiais": [],
                "total_itens": 0,
                "total_valor": Decimal("0.00"),
            }

        salas_map[sala_key]["materiais"].append(material)
        salas_map[sala_key]["total_itens"] += 1
        salas_map[sala_key]["total_valor"] += material.valor or Decimal("0.00")

    return render(request, "painel_materiais.html", {
        "sabados": sabados,
        "sabado": sabado,
        "tipo_local": tipo_local,
        "tipo_painel": tipo_painel,
        "tipo_local_opcoes": TIPO_LOCAL,
        "total_itens": total_itens,
        "total_valor": total_valor,
        "salas_map": list(salas_map.values()),
        "pedidos_map": [],
    })


def salvar_materiais_lote(request):
    if request.method != "POST":
        return redirect("supply:painel_materiais")

    sabado_id = request.POST.get("sabado")
    tipo_local = request.POST.get("tipo_local")
    tipo_painel = request.POST.get("painel", "material")

    if tipo_painel == "pedido":
        pedido_ids = request.POST.getlist("pedido_ids")

        for pedido_id in pedido_ids:
            try:
                pedido = Pedido.objects.get(pk=pedido_id)
            except Pedido.DoesNotExist:
                continue

            valor = request.POST.get(f"valor_pedido_{pedido_id}")
            local_compra = request.POST.get(f"local_compra_pedido_{pedido_id}")
            tipo_local_item = request.POST.get(f"tipo_local_pedido_{pedido_id}")

            pedido.valor = valor if valor not in ["", None] else None
            pedido.local_compra = local_compra if local_compra not in ["", None] else None
            pedido.tipo_local = tipo_local_item if tipo_local_item not in ["", None] else None
            pedido.save()

        messages.success(request, "Pedidos atualizados com sucesso.")
        return redirect(f"{request.path}?sabado={sabado_id}&tipo_local={tipo_local}&painel=pedido")

    material_ids = request.POST.getlist("material_ids")

    for material_id in material_ids:
        try:
            material = Material.objects.get(pk=material_id)
        except Material.DoesNotExist:
            continue

        valor = request.POST.get(f"valor_{material_id}")
        local_compra = request.POST.get(f"local_compra_{material_id}")
        tipo_local_item = request.POST.get(f"tipo_local_{material_id}")

        material.valor = valor if valor not in ["", None] else None
        material.local_compra = local_compra if local_compra not in ["", None] else None
        material.tipo_local = tipo_local_item if tipo_local_item not in ["", None] else None
        material.save()

    messages.success(request, "Materiais atualizados com sucesso.")
    return redirect(f"{request.path}?sabado={sabado_id}&tipo_local={tipo_local}&painel=material")

def painel_materiais_visualizacao(request):
    sabado_id = request.GET.get("sabado")
    tipo_local = request.GET.get("tipo_local")
    tipo_painel = request.GET.get("painel", "material")

    sabados = Sabado.objects.order_by("-data")[:40]
    pedidos_opcoes = PEDIDO

    if sabado_id:
        sabado = get_object_or_404(Sabado, pk=sabado_id)
    else:
        sabado = Sabado.objects.order_by("-data").first()

    if sabado is None:
        return render(request, "painel_materiais_visualizacao.html", {
            "sabados": sabados,
            "sabado": None,
            "tipo_local": tipo_local,
            "tipo_painel": tipo_painel,
            "tipo_local_opcoes": TIPO_LOCAL,
            "total_itens": 0,
            "total_valor": Decimal("0.00"),
            "salas_map": [],
            "pedidos_map": [],
        })

    if tipo_painel == "pedido":
        qs = (
            Pedido.objects
            .select_related("requisitado_por", "sabado")
            .filter(sabado=sabado)
            .order_by("area", "nome")
        )

        if tipo_local:
            qs = qs.filter(tipo_local=tipo_local)

        total_itens = qs.count()
        total_valor = qs.aggregate(
            total=Coalesce(
                Sum("valor"),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
            )
        )["total"] or Decimal("0.00")

        nomes_areas = dict(LISTA_AREAS)
        pedidos_map = OrderedDict()

        for item in qs:
            area_key = item.area or "SEM_AREA"
            area_nome = nomes_areas.get(area_key, "Sem área" if area_key == "SEM_AREA" else area_key)

            if area_key not in pedidos_map:
                pedidos_map[area_key] = {
                    "key": area_key,
                    "nome": area_nome,
                    "pedidos": [],
                    "total_itens": 0,
                    "total_valor": Decimal("0.00"),
                }

            pedidos_map[area_key]["pedidos"].append(item)
            pedidos_map[area_key]["total_itens"] += 1
            pedidos_map[area_key]["total_valor"] += item.valor or Decimal("0.00")

        return render(request, "painel_materiais_visualizacao.html", {
            "sabados": sabados,
            "sabado": sabado,
            "tipo_local": tipo_local,
            "tipo_painel": tipo_painel,
            "pedidos_opcoes": pedidos_opcoes,
            "tipo_local_opcoes": TIPO_LOCAL,
            "total_itens": total_itens,
            "total_valor": total_valor,
            "salas_map": [],
            "pedidos_map": list(pedidos_map.values()),
        })

    qs = (
    Material.objects
    .select_related("atividade__semanario", "atividade__semanario__data")
    .filter(atividade__semanario__data=sabado)
    # Supply = destino explícito "SUPPLY" OU sem destino definido (nulo/vazio)
    .filter(Q(pedido="SUPPLY") | Q(pedido__isnull=True) | Q(pedido=""))
    .order_by("atividade__semanario__sala", "nome")
)

    if tipo_local:
        qs = qs.filter(tipo_local=tipo_local)

    total_itens = qs.count()
    total_valor = qs.aggregate(
        total=Coalesce(
            Sum("valor"),
            Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
        )
    )["total"] or Decimal("0.00")

    nomes_salas = dict(LISTA_SALAS)
    salas_map = OrderedDict()

    for material in qs:
        sala_key = material.atividade.semanario.sala
        sala_nome = nomes_salas.get(sala_key, sala_key)

        if sala_key not in salas_map:
            salas_map[sala_key] = {
                "key": sala_key,
                "nome": sala_nome,
                "materiais": [],
                "total_itens": 0,
                "total_valor": Decimal("0.00"),
            }

        salas_map[sala_key]["materiais"].append(material)
        salas_map[sala_key]["total_itens"] += 1
        salas_map[sala_key]["total_valor"] += material.valor or Decimal("0.00")

    return render(request, "painel_materiais_visualizacao.html", {
        "sabados": sabados,
        "sabado": sabado,
        "tipo_local": tipo_local,
        "tipo_painel": tipo_painel,
        "pedidos_opcoes": pedidos_opcoes,
        "tipo_local_opcoes": TIPO_LOCAL,
        "total_itens": total_itens,
        "total_valor": total_valor,
        "salas_map": list(salas_map.values()),
        "pedidos_map": [],
    })



@login_required
def adicionar_pedidos(request):

    if request.user.area not in ["SUPPLY","TRIADE","PROJETOS","EVENTOS","GESTAO_DE_TALENTOS","RECREACAO","ADM/FIN","CR/RE","MARKETING",]:
        messages.error(request, "Você não tem permissão para acessar esta página.")
        return redirect("/supply/")

    queryset = Pedido.objects.none()

    if request.method == "POST":
        import logging
        logger = logging.getLogger("django")
        formset = PedidoFormSet(request.POST, queryset=queryset)

        logger.info("POST recebido em adicionar_pedidos")
        logger.info(f"Dados recebidos: {request.POST}")
        logger.info(f"Formset is_valid: {formset.is_valid()}")
        logger.info(f"Formset total forms: {formset.total_form_count()}")

        if formset.is_valid():
            pedidos_para_salvar = []
            algum_formulario_preenchido = False

            for idx, form in enumerate(formset):
                logger.info(f"Form {idx} cleaned_data: {form.cleaned_data}")
                if not form.cleaned_data:
                    logger.info(f"Form {idx} ignorado: cleaned_data vazio")
                    continue

                nome = form.cleaned_data.get("nome")
                if nome:
                    algum_formulario_preenchido = True
                    pedido = form.save(commit=False)
                    pedido.requisitado_por = request.user
                    pedidos_para_salvar.append(pedido)
                    logger.info(f"Form {idx} pronto para salvar: nome={nome}")
                else:
                    if any(
                        form.cleaned_data.get(campo)
                        for campo in ["quantidade", "unidade", "sabado", "area"]
                    ):
                        form.add_error("nome", "Preencha o nome do pedido.")
                        logger.info(f"Form {idx} erro: nome não preenchido, mas outros campos sim")

            tem_erros = any(form.errors for form in formset)
            logger.info(f"Pedidos para salvar: {len(pedidos_para_salvar)} | Algum preenchido: {algum_formulario_preenchido} | Tem erros: {tem_erros}")

            if tem_erros:
                messages.error(request, "Corrija os erros antes de salvar.")
            elif not algum_formulario_preenchido:
                messages.warning(request, "Adicione pelo menos um pedido para salvar.")
            else:
                with transaction.atomic():
                    for pedido in pedidos_para_salvar:
                        pedido.save()
                logger.info("Pedidos salvos com sucesso!")
                messages.success(request, "Pedidos cadastrados com sucesso.")
                return redirect("supply:adicionar_pedidos")
        else:
            logger.info(f"Formset inválido: errors={formset.errors}")
            messages.error(request, "Corrija os erros antes de salvar.")

    else:
        formset = PedidoFormSet(queryset=queryset)

    return render(request, "adicionar_pedidos.html", {
        "formset": formset,
    })

    
class SupplyView(LoginRequiredMixin, TemplateView):
    template_name = "supply_view.html"


@login_required
def meus_pedidos(request):

    if request.user.area not in ["SUPPLY","TRIADE","PROJETOS","EVENTOS","GESTAO_DE_TALENTOS","RECREACAO","ADM/FIN","CR/RE","MARKETING",]:
        messages.error(request, "Você não tem permissão para acessar esta página.")
        return redirect("/supply/")
    
    sabado_id = request.GET.get("sabado")

    sabados = Sabado.objects.order_by("-data")[:40]

    qs = Pedido.objects.filter(requisitado_por=request.user).order_by("-id")

    if sabado_id:
        qs = qs.filter(sabado_id=sabado_id)

    PedidoFormSet = modelformset_factory(
        Pedido,
        form=MeuPedidoForm,
        extra=1,
        can_delete=True
    )

    if request.method == "POST":
        formset = PedidoFormSet(
            request.POST,
            queryset=Pedido.objects.filter(requisitado_por=request.user)
        )

        if formset.is_valid():
            instances = formset.save(commit=False)

            for obj in formset.deleted_objects:
                if obj.requisitado_por == request.user:
                    obj.delete()

            for pedido in instances:
                pedido.requisitado_por = request.user
                pedido.save()

            messages.success(request, "Pedidos atualizados com sucesso.")
            return redirect("supply:meus_pedidos")

        messages.error(request, "Corrija os erros antes de salvar.")
    else:
        formset = PedidoFormSet(queryset=qs)

    return render(request, "meus_pedidos.html", {
        "formset": formset,
        "sabados": sabados,
        "sabado_id": sabado_id,
    })