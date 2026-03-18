from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Item, Movimentacao
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
    sabado_id = request.GET.get("sabado")

    sabados = Sabado.objects.order_by("-data")[:40]

    if sabado_id:
        sabado = get_object_or_404(Sabado, pk=sabado_id)
    else:
        sabado = Sabado.objects.order_by("-data").first()

    if sabado is None:
        return render(request, "painel_materiais.html", {
            "sabados": sabados,
            "sabado": None,
            "tipo_local_opcoes": TIPO_LOCAL,
            "total_itens": 0,
            "total_valor": Decimal("0.00"),
            "salas_map": [],
        })

    # 🔥 FILTRO FIXO
    qs = (
        Material.objects
        .select_related("atividade__semanario", "atividade__semanario__data")
        .filter(
            atividade__semanario__data=sabado,
            pedido="SUPPLY"
        )
        .order_by("atividade__semanario__sala", "nome")
    )

    total_itens = qs.count()

    total_valor = qs.aggregate(
        total=Coalesce(
            Sum("valor"),
            Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
        )
    )["total"] or Decimal("0.00")

    salas_map = OrderedDict()
    for key, nome in LISTA_SALAS:
        salas_map[key] = {
            "key": key,
            "nome": nome,
            "materiais": [],
            "total_itens": 0,
            "total_valor": Decimal("0.00"),
        }

    for material in qs:
        sala_key = material.atividade.semanario.sala

        if sala_key not in salas_map:
            salas_map[sala_key] = {
                "key": sala_key,
                "nome": sala_key,
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
        "tipo_local_opcoes": TIPO_LOCAL,
        "total_itens": total_itens,
        "total_valor": total_valor,
        "salas_map": list(salas_map.values()),
    })


def salvar_materiais_lote(request):
    if request.method != "POST":
        return redirect("supply:painel_materiais")

    material_ids = request.POST.getlist("material_ids")

    atualizados = 0
    erros = []

    for material_id in material_ids:
        try:
            material = Material.objects.get(pk=material_id)
        except Material.DoesNotExist:
            erros.append(f"Material ID {material_id} não encontrado.")
            continue

        valor_raw = request.POST.get(f"valor_{material_id}", "").strip()
        local_compra = request.POST.get(f"local_compra_{material_id}", "").strip()
        tipo_local = request.POST.get(f"tipo_local_{material_id}", "").strip()

        if valor_raw:
            valor_raw = valor_raw.replace(",", ".")
            try:
                material.valor = Decimal(valor_raw)
            except InvalidOperation:
                erros.append(f"Valor inválido no material '{material.nome}'.")
                continue
        else:
            material.valor = None

        material.local_compra = local_compra or None
        material.tipo_local = tipo_local or None
        material.save()

        atualizados += 1

    if atualizados:
        messages.success(request, f"{atualizados} material(is) atualizado(s) com sucesso.")

    for erro in erros:
        messages.error(request, erro)

    base_url = reverse("supply:painel_materiais")
    sabado_id = request.POST.get("sabado")

    if sabado_id:
        return redirect(f"{base_url}?sabado={sabado_id}")

    return redirect(base_url)


def painel_materiais_visualizacao(request):
    sabado_id = request.GET.get("sabado")
    pedido = request.GET.get("pedido")

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
            "pedido": pedido,
            "pedidos_opcoes": pedidos_opcoes,
            "total_itens": 0,
            "total_valor": Decimal("0.00"),
            "salas_map": [],
        })

    qs = (
        Material.objects
        .select_related("atividade__semanario", "atividade__semanario__data")
        .filter(atividade__semanario__data=sabado)
        .order_by("atividade__semanario__sala", "nome")
    )

    if pedido:
        qs = qs.filter(pedido=pedido)

    total_itens = qs.count()

    total_valor = qs.aggregate(
        total=Coalesce(
            Sum("valor"),
            Value(0, output_field=DecimalField(max_digits=12, decimal_places=2))
        )
    )["total"] or Decimal("0.00")

    salas_map = OrderedDict()
    for key, nome in LISTA_SALAS:
        salas_map[key] = {
            "key": key,
            "nome": nome,
            "materiais": [],
            "total_itens": 0,
            "total_valor": Decimal("0.00"),
        }

    for material in qs:
        sala_key = material.atividade.semanario.sala

        if sala_key not in salas_map:
            salas_map[sala_key] = {
                "key": sala_key,
                "nome": sala_key,
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
        "pedido": pedido,
        "pedidos_opcoes": pedidos_opcoes,
        "total_itens": total_itens,
        "total_valor": total_valor,
        "salas_map": list(salas_map.values()),
    })