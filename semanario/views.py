from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.forms import modelformset_factory
from django.views.generic import ListView, DetailView, TemplateView
import json
from decimal import Decimal, InvalidOperation
from django.db.models import IntegerField, Value
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from django.db.models.functions import Coalesce
from datetime import datetime, timedelta
from atendido.models import PresencaAtendido
from voluntario.models import PresencaVoluntario
from .models import LISTA_SALAS, Semanario, Atividade, Material
from .forms import SemanarioForm, AtividadeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from sabado.models import Sabado, DisponibilidadeVoluntario
from supply.models import Item
from django.db.models import Prefetch, Count

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
                        item = Item.objects.filter(pk=m.get('item_id'), ativo=True).first()
                        link = m.get('link', '').strip()
                        quantidade = m.get('quantidade', '').strip()
                        unidade = m.get('unidade', '').strip()
                        # Sem destino explícito → Supply (padrão de compra do projeto)
                        pedido = m.get('pedido', '').strip() or 'SUPPLY'
                        if item:
                            # validar quantidade, usando default 1 quando vazio ou inválido
                            if quantidade:
                                try:
                                    qtd = Decimal(quantidade)
                                except (InvalidOperation, TypeError):
                                    qtd = Decimal('1')
                            else:
                                qtd = Decimal('1')
                            Material.objects.create(
                                atividade=atividade_obj,
                                item=item,
                                link=link,
                                quantidade=qtd,
                                unidade=(unidade or 'UN'),
                                pedido=pedido
                            )

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

    return render(request, "criar_semanario.html", {
        "semanario_form": semanario_form,
        "formset": formset,
        "itens": Item.objects.filter(ativo=True).order_by("nome"),
    })


# Salvar materiais via modal
def adicionar_material(request, atividade_id):
    if request.method == "POST":
        atividade = get_object_or_404(Atividade, id=atividade_id)
        item = Item.objects.filter(pk=request.POST.get("item_id"), ativo=True).first()
        link = request.POST.get("link", "").strip()
        quantidade = request.POST.get("quantidade")
        unidade = request.POST.get("unidade")

        if item:
            Material.objects.create(atividade=atividade, item=item, link=link, quantidade=quantidade, unidade=unidade)
            return JsonResponse({"success": True})
    return JsonResponse({"success": False})

class SemanarioView(LoginRequiredMixin, TemplateView):
    template_name = "semanario_view.html"

def editar_semanario(request, semanario_id):
    semanario = get_object_or_404(Semanario, id=semanario_id)
    existing_count = semanario.atividades.count()
    extras = max(0, 5 - existing_count)
    AtividadeFormSet = modelformset_factory(Atividade, form=AtividadeForm, extra=extras, can_delete=False)

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
                            item = Item.objects.filter(pk=m.get('item_id'), ativo=True).first()
                            link = m.get('link', '').strip()
                            quantidade = m.get('quantidade', '').strip()
                            unidade = m.get('unidade', '').strip()
                            # Sem destino explícito → Supply (padrão de compra do projeto)
                            pedido = m.get('pedido', '').strip() or 'SUPPLY'
                            if item:
                                if quantidade:
                                    try:
                                        qtd = Decimal(quantidade)
                                    except (InvalidOperation, TypeError):
                                        qtd = Decimal('1')
                                else:
                                    qtd = Decimal('1')
                                Material.objects.create(
                                    atividade=atividade_obj, item=item, link=link, quantidade=qtd,
                                    unidade=(unidade or 'UN'), pedido=pedido
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
        "semanario": semanario,
        "itens": Item.objects.filter(ativo=True).order_by("nome"),
    })

class SemanarioListView(LoginRequiredMixin, ListView):
    model = Semanario
    template_name = "lista_semanarios.html"
    context_object_name = "semanarios"

    def get_queryset(self):
        return Semanario.objects.select_related("data").order_by("-data__data")

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
            "item_id": m.item_id,
            "link": m.link,
            "quantidade": str(m.quantidade),
            "unidade": m.unidade,
            "pedido": m.pedido if hasattr(m, 'pedido') else ''
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
            item=get_object_or_404(Item, pk=m.get("item_id"), ativo=True),
            link=(m.get("link") or "").strip(),
            quantidade=m["quantidade"],
            unidade=m["unidade"],
            # Sem destino explícito → Supply (padrão de compra do projeto)
            pedido=(m.get("pedido") or "").strip() or "SUPPLY",
        )
    return JsonResponse({"success": True})


class VisualizarSemanario(LoginRequiredMixin, DetailView):
    model = Semanario
    template_name = "visualizar_semanario.html"
    context_object_name = "semanario"
    pk_url_kwarg = "semanario_id"


def painel_sabado_educ(request):
    # filtro por sábado via GET ?sabado=ID
    sabados = Sabado.objects.order_by("-data")[:30]  # lista pro dropdown

    sabado_id = request.GET.get("sabado")
    if sabado_id:
        sabado = get_object_or_404(Sabado, pk=sabado_id)
    else:
        # padrão: próximo sábado (ou o mais recente futuro)
        sabado = Sabado.objects.order_by("data").first()

    # atividades com responsável já carregado
    atividades_qs = Atividade.objects.select_related("responsavel").only(
        "id", "semanario_id", "atividade", "local", "tempo_atividade", "responsavel__first_name"
    )

    semanarios = (
        Semanario.objects
        .filter(data=sabado)
        .prefetch_related(
            "talentos_necessarios",
            Prefetch("atividades", queryset=atividades_qs),
        )
    )

    # Mapa sala -> semanário (ou None)
    sem_por_sala = {sala_key: None for sala_key, _ in LISTA_SALAS}
    for s in semanarios:
        sem_por_sala[s.sala] = s

    # Contagem de voluntários por sala que VÃO ao projeto nesse sábado
    # ⚠️ Ajuste "voluntario__sala" se o seu model Voluntario usar outro campo!
    voluntarios_por_sala = (
        DisponibilidadeVoluntario.objects
        .filter(sabado=sabado, vai_ao_projeto=True)
        .values("voluntario__area")
        .annotate(total=Count("id"))
    )
    voluntarios_map = {row["voluntario__area"]: row["total"] for row in voluntarios_por_sala}

    # Monta cards prontos pro template (mais fácil de renderizar)
    cards = []
    for sala_key, sala_nome in LISTA_SALAS:
        sem = sem_por_sala[sala_key]

        if sem:
            locais = sorted({a.local for a in sem.atividades.all() if a.local})
            talentos = list(sem.talentos_necessarios.all())
            atividades = list(sem.atividades.all())
            precisa_projetor = sem.projetor
            vagas = sem.vagas
            tema = sem.tema
        else:
            locais, talentos, atividades = [], [], []
            precisa_projetor = False
            vagas = 0
            tema = None

        cards.append({
            "sala_key": sala_key,
            "sala_nome": sala_nome,
            "semanario": sem,
            "tema": tema,
            "projetor": precisa_projetor,
            "vagas": vagas,
            "talentos": talentos,
            "locais": locais,
            "atividades": atividades,
            "voluntarios_confirmados": voluntarios_map.get(sala_key, 0),
        })

    # Resumos “de topo” (pra bater o olho)
    salas_com_projetor = [c["sala_nome"] for c in cards if c["projetor"]]
    total_vagas = sum(c["vagas"] for c in cards)
    total_voluntarios = sum(c["voluntarios_confirmados"] for c in cards)

    return render(request, "painel_sabado_educ.html", {
        "sabados": sabados,
        "sabado": sabado,
        "cards": cards,
        "salas_com_projetor": salas_com_projetor,
        "total_vagas": total_vagas,
        "total_voluntarios": total_voluntarios,
    })



def relatorio_pedagogico(request):
    # ======= filtros =======
    sala = request.GET.get("sala")  # ex: "AZUL"
    dt_ini_str = request.GET.get("inicio")
    dt_fim_str = request.GET.get("fim")

    # defaults: últimos 90 dias
    hoje = timezone.now().date()
    dt_ini = hoje - timedelta(days=90)
    dt_fim = hoje

    if dt_ini_str:
        try:
            dt_ini = datetime.strptime(dt_ini_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    if dt_fim_str:
        try:
            dt_fim = datetime.strptime(dt_fim_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    # ======= queryset base (semanários no período) =======
    sem_qs = Semanario.objects.filter(
        data__data__gte=dt_ini,
        data__data__lte=dt_fim,
    )
    if sala:
        sem_qs = sem_qs.filter(sala=sala)

    # sábados considerados no relatório (somente onde existe semanário no filtro)
    sabados_ids = list(sem_qs.values_list("data_id", flat=True).distinct())
    qtd_sabados = len(sabados_ids)

    # ======= atividades e materiais do recorte =======
    atv_qs = Atividade.objects.filter(semanario__in=sem_qs)
    mat_qs = Material.objects.filter(atividade__semanario__in=sem_qs)

    # ======= cards do topo =======
    qtd_atividades = atv_qs.count()

    from django.db.models import IntegerField, DecimalField, FloatField, Value
    total_minutos = atv_qs.aggregate(
        total=Coalesce(Sum("tempo_atividade", output_field=IntegerField()), Value(0, output_field=IntegerField()))
    )["total"] or 0

    # Materiais:
    # - total_itens_material = quantidade de linhas
    # - total_quantidade_material = soma de quantidades (mistura unidades; útil como “volume de registros”, não de estoque)
    total_itens_material = mat_qs.count()
    total_quantidade_material = mat_qs.aggregate(
        total=Coalesce(Sum("quantidade", output_field=DecimalField()), Value(0, output_field=DecimalField()))
    )["total"] or 0

    # ======= análises =======

    # 1) horas por competência (soma de minutos por competência)
    minutos_por_competencia = (
        atv_qs.values("competencia")
        .annotate(
            minutos=Coalesce(Sum("tempo_atividade", output_field=IntegerField()), Value(0, output_field=IntegerField()))
        )
        .order_by("-minutos")
    )
    
    horas_por_competencia = [
        {
            "competencia": row["competencia"] or "(sem competência)",
            "horas": round((row["minutos"] or 0) / 60, 2),
            "minutos": int(row["minutos"] or 0),
        }
        for row in minutos_por_competencia
    ]

    # 2) nº médio de atividades por sábado
    media_ativ_por_sabado = round(qtd_atividades / qtd_sabados, 2) if qtd_sabados else 0

    # 3) média de vagas abertas
    media_vagas = sem_qs.aggregate(
        media=Coalesce(Avg("vagas", output_field=FloatField()), Value(0, output_field=FloatField()))
    )["media"] or 0
    media_vagas = round(media_vagas, 2)

    # 4) frequência de uso de projetor (%)
    total_semanarios = sem_qs.count()
    qtd_projetor = sem_qs.filter(projetor=True).count()
    freq_projetor = round((qtd_projetor / total_semanarios) * 100, 1) if total_semanarios else 0

    # 5) locais mais usados
    locais_mais_usados = (
        atv_qs.values("local")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    # 6) presença real de atendidos (por sábado): Presente + Justificada
    pres_at_qs = PresencaAtendido.objects.filter(
        data_id__in=sabados_ids
    )

    if sala:
        # ⚠️ Ajuste aqui se o seu Atendido NÃO tiver campo "sala"
        # Ex.: atendido__salinha ou atendido__area
        pres_at_qs = pres_at_qs.filter(atendido__sala=sala)

    pres_at_presentes = pres_at_qs.filter(presenca__in=["PRESENTE", "JUSTIFICADA"]).count()
    media_presenca_atendidos = round(pres_at_presentes / qtd_sabados, 2) if qtd_sabados else 0

    # 7) presença real de voluntários (por sábado): Presente + Justificada
    pres_vol_qs = PresencaVoluntario.objects.filter(
        data_id__in=sabados_ids
    )

    if sala:
        # voluntários daquela salinha (assumindo area = sala)
        pres_vol_qs = pres_vol_qs.filter(voluntario__area=sala)

    pres_vol_presentes = pres_vol_qs.filter(presenca__in=["PRESENTE", "JUSTIFICADA"]).count()
    media_presenca_voluntarios = round(pres_vol_presentes / qtd_sabados, 2) if qtd_sabados else 0

    # Extras úteis: materiais mais usados (top 10 por nome)
    materiais_top = (
        mat_qs.values("nome")
        .annotate(total_itens=Count("id"))
        .order_by("-total_itens")[:10]
    )

    context = {
        "lista_salas": LISTA_SALAS,
        "filtro_sala": sala,
        "inicio": dt_ini,
        "fim": dt_fim,

        # cards
        "qtd_sabados": qtd_sabados,
        "qtd_atividades": qtd_atividades,
        "total_minutos": int(total_minutos),
        "total_horas": round(total_minutos / 60, 2),
        "total_itens_material": total_itens_material,
        "total_quantidade_material": total_quantidade_material,

        # análises
        "horas_por_competencia": horas_por_competencia,
        "media_ativ_por_sabado": media_ativ_por_sabado,
        "media_vagas": media_vagas,
        "freq_projetor": freq_projetor,
        "locais_mais_usados": locais_mais_usados,
        "media_presenca_atendidos": media_presenca_atendidos,
        "media_presenca_voluntarios": media_presenca_voluntarios,
        "materiais_top": materiais_top,
    }
    return render(request, "relatorio_pedagogico.html", context)
