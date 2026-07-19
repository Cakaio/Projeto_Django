from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import modelformset_factory
from .forms import MeuPedidoForm
from supply.forms import PedidoFormSet
from .models import Item, Local, Movimentacao, Pedido, UNIDADES
from django.shortcuts import render, redirect
from django.db.models import Prefetch
from semanario.models import Material
from sabado.models import Sabado
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Count, Q, Value, DecimalField, F, ExpressionWrapper
from django.db.models.functions import Coalesce
from sabado.models import Sabado
from semanario.models import Material, LISTA_SALAS, PEDIDO, UNIDADES as UNIDADES_MATERIAL
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from voluntario.models import Voluntario, LISTA_AREAS


VALOR_TOTAL_EXPRESSION = ExpressionWrapper(
    F("valor") * F("quantidade"),
    output_field=DecimalField(max_digits=18, decimal_places=2),
)


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
    local_id = request.GET.get("local")
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
            "locais": Local.objects.filter(ativo=True),
            "unidades": UNIDADES,
            "total_itens": 0,
            "total_valor": Decimal("0.00"),
            "salas_map": [],
            "pedidos_map": [],
        })

    if tipo_painel == "pedido":
        qs = (
            Pedido.objects
            .select_related("requisitado_por", "sabado", "local")
            .filter(sabado=sabado)
            .order_by("area", "nome")
        )

        if local_id:
            qs = qs.filter(local_id=local_id)

        total_itens = qs.count()
        total_valor = qs.aggregate(
            total=Coalesce(
                Sum(VALOR_TOTAL_EXPRESSION),
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
            pedidos_map[area_key]["total_valor"] += pedido.valor_total or Decimal("0.00")

        return render(request, "painel_materiais.html", {
            "sabados": sabados,
            "sabado": sabado,
            "local_id": local_id,
            "tipo_painel": tipo_painel,
            "locais": Local.objects.filter(ativo=True),
            "unidades": UNIDADES,
            "total_itens": total_itens,
            "total_valor": total_valor,
            "salas_map": [],
            "pedidos_map": list(pedidos_map.values()),
        })

    qs = (
        Material.objects
        .select_related("atividade__semanario", "atividade__semanario__data", "local")
        .filter(atividade__semanario__data=sabado)
        # Supply = destino explícito "SUPPLY" OU sem destino definido (nulo/vazio)
        .filter(Q(pedido="SUPPLY") | Q(pedido__isnull=True) | Q(pedido=""))
        .order_by("atividade__semanario__sala", "nome")
    )

    if local_id:
        qs = qs.filter(local_id=local_id)

    total_itens = qs.count()
    total_valor = qs.aggregate(
        total=Coalesce(
            Sum(VALOR_TOTAL_EXPRESSION),
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
        salas_map[sala_key]["total_valor"] += material.valor_total or Decimal("0.00")

    return render(request, "painel_materiais.html", {
        "sabados": sabados,
        "sabado": sabado,
        "local_id": local_id,
        "tipo_painel": tipo_painel,
        "locais": Local.objects.filter(ativo=True),
        "unidades_material": UNIDADES_MATERIAL,
        "total_itens": total_itens,
        "total_valor": total_valor,
        "salas_map": list(salas_map.values()),
        "pedidos_map": [],
    })


def salvar_materiais_lote(request):
    if request.method != "POST":
        return redirect("supply:painel_materiais")

    sabado_id = request.POST.get("sabado")
    local_id = request.POST.get("local")
    tipo_painel = request.POST.get("painel", "material")

    if tipo_painel == "pedido":
        pedido_ids = request.POST.getlist("pedido_ids")
        pedidos_com_erro = []

        for pedido_id in pedido_ids:
            try:
                pedido = Pedido.objects.get(pk=pedido_id)
            except Pedido.DoesNotExist:
                continue

            valor = request.POST.get(f"valor_pedido_{pedido_id}")
            pedido_local_id = request.POST.get(f"local_pedido_{pedido_id}")
            nome = request.POST.get(f"nome_pedido_{pedido_id}", "").strip()
            quantidade = request.POST.get(f"quantidade_pedido_{pedido_id}")
            unidade = request.POST.get(f"unidade_pedido_{pedido_id}")

            try:
                quantidade_decimal = Decimal(quantidade)
                if quantidade_decimal < 0:
                    raise ValueError("A quantidade não pode ser negativa.")
                pedido.nome = nome
                pedido.quantidade = quantidade_decimal
                pedido.unidade = unidade
                pedido.valor = Decimal(valor) if valor not in ["", None] else None
                pedido.local_id = pedido_local_id or None
                pedido.full_clean()
                pedido.save()
            except (InvalidOperation, TypeError, ValidationError, ValueError):
                pedidos_com_erro.append(pedido.nome or f"ID {pedido_id}")

        if pedidos_com_erro:
            messages.error(
                request,
                "Alguns pedidos não foram salvos. Verifique nome, quantidade, unidade e valor: "
                + ", ".join(pedidos_com_erro),
            )
        else:
            messages.success(request, "Pedidos atualizados com sucesso.")
        return redirect(f"{request.path}?sabado={sabado_id}&local={local_id or ''}&painel=pedido")

    material_ids = request.POST.getlist("material_ids")
    materiais_com_erro = []

    for material_id in material_ids:
        try:
            material = Material.objects.get(pk=material_id)
        except Material.DoesNotExist:
            continue

        valor = request.POST.get(f"valor_{material_id}")
        material_local_id = request.POST.get(f"local_{material_id}")
        nome = request.POST.get(f"nome_material_{material_id}", "").strip()
        quantidade = request.POST.get(f"quantidade_material_{material_id}")
        unidade = request.POST.get(f"unidade_material_{material_id}")

        try:
            quantidade_decimal = Decimal(quantidade)
            if quantidade_decimal < 0:
                raise ValueError("A quantidade não pode ser negativa.")
            material.nome = nome
            material.quantidade = quantidade_decimal
            material.unidade = unidade
            material.valor = Decimal(valor) if valor not in ["", None] else None
            material.local_id = material_local_id or None
            material.full_clean()
            material.save()
        except (InvalidOperation, TypeError, ValidationError, ValueError):
            materiais_com_erro.append(material.nome or f"ID {material_id}")

    if materiais_com_erro:
        messages.error(
            request,
            "Alguns materiais não foram salvos. Verifique nome, quantidade, unidade e valor: "
            + ", ".join(materiais_com_erro),
        )
    else:
        messages.success(request, "Materiais atualizados com sucesso.")
    return redirect(f"{request.path}?sabado={sabado_id}&local={local_id or ''}&painel=material")

def painel_materiais_visualizacao(request):
    sabado_id = request.GET.get("sabado")
    local_id = request.GET.get("local")
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
            "local_id": local_id,
            "tipo_painel": tipo_painel,
            "locais": Local.objects.filter(ativo=True),
            "total_itens": 0,
            "total_valor": Decimal("0.00"),
            "salas_map": [],
            "pedidos_map": [],
        })

    if tipo_painel == "pedido":
        qs = (
            Pedido.objects
            .select_related("requisitado_por", "sabado", "local")
            .filter(sabado=sabado)
            .order_by("area", "nome")
        )

        if local_id:
            qs = qs.filter(local_id=local_id)

        total_itens = qs.count()
        total_valor = qs.aggregate(
            total=Coalesce(
                Sum(VALOR_TOTAL_EXPRESSION),
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
            pedidos_map[area_key]["total_valor"] += item.valor_total or Decimal("0.00")

        return render(request, "painel_materiais_visualizacao.html", {
            "sabados": sabados,
            "sabado": sabado,
            "local_id": local_id,
            "tipo_painel": tipo_painel,
            "pedidos_opcoes": pedidos_opcoes,
            "locais": Local.objects.filter(ativo=True),
            "total_itens": total_itens,
            "total_valor": total_valor,
            "salas_map": [],
            "pedidos_map": list(pedidos_map.values()),
        })

    qs = (
    Material.objects
    .select_related("atividade__semanario", "atividade__semanario__data", "local")
    .filter(atividade__semanario__data=sabado)
    # Supply = destino explícito "SUPPLY" OU sem destino definido (nulo/vazio)
    .filter(Q(pedido="SUPPLY") | Q(pedido__isnull=True) | Q(pedido=""))
    .order_by("atividade__semanario__sala", "nome")
)

    if local_id:
        qs = qs.filter(local_id=local_id)

    total_itens = qs.count()
    total_valor = qs.aggregate(
        total=Coalesce(
            Sum(VALOR_TOTAL_EXPRESSION),
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
        salas_map[sala_key]["total_valor"] += material.valor_total or Decimal("0.00")

    return render(request, "painel_materiais_visualizacao.html", {
        "sabados": sabados,
        "sabado": sabado,
        "local_id": local_id,
        "tipo_painel": tipo_painel,
        "pedidos_opcoes": pedidos_opcoes,
        "locais": Local.objects.filter(ativo=True),
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
                        for campo in ["link", "quantidade", "unidade", "sabado", "area"]
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
