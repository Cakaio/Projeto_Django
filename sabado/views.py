from collections import defaultdict
from urllib import request
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

import sabado
from .models import Sabado, DisponibilidadeVoluntario, FaixaHorarioAjuda
from .forms import DisponibilidadeForm
from voluntario.models import Voluntario, Talento, LISTA_AREAS, TIPO_ALIMENTACAO
from django.db.models import Count, Q, Prefetch
# Create your views here.

@login_required
def responder_disponibilidade(request, sabado_id):
    sabado = get_object_or_404(Sabado, pk=sabado_id)

    if not sabado.enquete_aberta:
        messages.error(request, "⚠️ Esta enquete já foi encerrada.")
        return redirect("inicio")

    # Busca a resposta existente, se houver. NÃO cria no GET.
    #
    # Antes isto era um get_or_create fora do `if POST`: só ABRIR a tela já
    # gravava uma resposta com vai_ao_projeto=False. A pessoa era contada como
    # respondente em todo lugar (o resumo e o lembrete definem "respondeu" como
    # "tem linha de disponibilidade"), e ainda aparecia para a liderança como
    # "não vai ao projeto" sem nunca ter dito isso.
    #
    # Com o lembrete diário isso deixaria de ser azar e viraria regra: o push
    # leva a pessoa à tela, ela olha, fecha sem enviar — e nunca mais é cobrada
    # daquele sábado. Quanto melhor a notificação funcionasse, mais gente o bug
    # engoliria.
    obj = DisponibilidadeVoluntario.objects.filter(
        sabado=sabado, voluntario=request.user
    ).first()
    created = obj is None

    if request.method == "POST":
        form = DisponibilidadeForm(request.POST, instance=obj)

        if form.is_valid():
            resposta = form.save(commit=False)

            # garante no backend (anti-gambiarra no front)
            resposta.sabado = sabado
            resposta.voluntario = request.user

            resposta.save()
            form.save_m2m()  # salva o ManyToMany (pode_ajudar)

            messages.success(request, "✅ Resposta atualizada com sucesso!")
            return redirect("sabado:responder_disponibilidade", sabado_id=sabado.id)

        else:
            messages.error(request, "❌ Há erros no formulário. Confira os campos.")
    else:
        form = DisponibilidadeForm(instance=obj)

    return render(request, "responder_disponibilidade.html", {
        "sabado": sabado,
        "form": form,
        "created": created,  # opcional (debug)
    })

@login_required
def resumo_sabado(request):
    # dropdown com sábados recentes
    sabados = Sabado.objects.order_by("-data")[:40]

    sabado_id = request.GET.get("sabado")
    if sabado_id:
        sabado = get_object_or_404(Sabado, pk=sabado_id)
    else:
        # fallback: sábado mais recente
        sabado = Sabado.objects.order_by("-data").first()

    if not sabado:
        # caso não exista nenhum sábado cadastrado ainda
        return render(request, "resumo_sabado.html", {
            "sabados": sabados,
            "sabado": None,
            "erro": "Nenhum sábado cadastrado ainda.",
        })

    # Base: disponibilidades de quem VAI ao projeto nesse sábado
    disp_qs = (
        DisponibilidadeVoluntario.objects
        .filter(sabado=sabado, vai_ao_projeto=True)
        .select_related("voluntario")
        .prefetch_related("pode_ajudar")
    )

    total_voluntarios = disp_qs.count()

    # ====== QUEM DISSE QUE NÃO VAI ======
    # Responder "não vou" é resposta: some da fila de cobrança e vira
    # informação de planejamento (quantas mãos faltam no sábado).
    disp_nao_vao = (
        DisponibilidadeVoluntario.objects
        .filter(sabado=sabado, vai_ao_projeto=False)
        .select_related("voluntario")
    )
    total_nao_vao = disp_nao_vao.count()

    # ====== QUEM AINDA NÃO RESPONDEU ======
    # Só entram voluntários ATIVOS: contar desligado ou login desativado
    # enchia a lista de gente que não tem como responder, e era justamente
    # esse número que a liderança usava para cobrar.
    nao_responderam_qs = (
        Voluntario.objects.ativos()
        .exclude(disponibilidades__sabado=sabado)
        .order_by("first_name", "last_name", "username")
    )
    total_nao_responderam = nao_responderam_qs.count()

    # Agrupado por área: cada líder cobra a própria equipe, em vez de encarar
    # uma lista única enorme.
    nao_responderam_map = defaultdict(list)
    for voluntario in nao_responderam_qs:
        nao_responderam_map[voluntario.area].append(voluntario)

    nao_responderam_por_area = [
        {"key": area_key, "nome": area_nome, "voluntarios": vols, "total": len(vols)}
        for area_key, area_nome in LISTA_AREAS
        if (vols := nao_responderam_map.get(area_key))
    ]
    # Área não preenchida existe no banco; sem isto o voluntário sumiria da
    # lista e ninguém iria cobrá-lo.
    sem_area = [v for v in nao_responderam_qs if not v.area]
    if sem_area:
        nao_responderam_por_area.append(
            {"key": "", "nome": "Sem área definida", "voluntarios": sem_area,
             "total": len(sem_area)})

    total_ativos = Voluntario.objects.ativos().count()
    total_responderam = total_ativos - total_nao_responderam
    percentual_resposta = (
        int(round(total_responderam / total_ativos * 100)) if total_ativos else 0
    )


    # ====== 1) Por área (com lista de voluntários) ======
    area_vols_map = defaultdict(list)
    for d in disp_qs:
        area_vols_map[d.voluntario.area].append(d.voluntario)

    por_area_lista = []
    for area_key, area_nome in LISTA_AREAS:
        vols = sorted(area_vols_map.get(area_key, []), key=lambda v: (v.get_full_name() or v.username).lower())
        por_area_lista.append({
            "key": area_key,
            "nome": area_nome,
            "total": len(vols),
            "voluntarios": vols,
        })

    # ====== 2) Ajuda por faixa (com nomes) ======
    faixas = FaixaHorarioAjuda.objects.order_by("descricao")

    # quem é "ajudante": marcou pelo menos uma faixa
    disp_com_ajuda = disp_qs.filter(pode_ajudar__isnull=False).distinct()
    total_ajudantes = disp_com_ajuda.count()

    faixa_para_vols = {f.id: {"faixa": f, "voluntarios": []} for f in faixas}

    for d in disp_com_ajuda:
        for f in d.pode_ajudar.all():
            faixa_para_vols[f.id]["voluntarios"].append(d.voluntario)

    faixa_cards = []
    for f in faixas:
        vols = faixa_para_vols[f.id]["voluntarios"]
        # opcional: ordenar por nome/username
        vols_sorted = sorted(vols, key=lambda v: (v.get_full_name() or v.username).lower())
        faixa_cards.append({
            "faixa": f,
            "total": len(vols_sorted),
            "voluntarios": vols_sorted,
        })

    # ====== 3) Carro ======
    total_carro = disp_qs.filter(vai_de_carro=True).count()
    total_nao_carro = disp_qs.filter(vai_de_carro=False).count()
    total_carro_nao_resp = disp_qs.filter(vai_de_carro__isnull=True).count()

    # ====== 4) Saúde (contagens + listas) ======
    disp_saude_ok = disp_qs.filter(saude=True)
    disp_saude_nao_ok = disp_qs.filter(saude=False)
    disp_saude_nao_resp = disp_qs.filter(saude__isnull=True)

    def voluntarios_from_disp(qs):
        vols = [d.voluntario for d in qs]
        return sorted(vols, key=lambda v: (v.get_full_name() or v.username).lower())

    saude = {
        "ok": {"total": disp_saude_ok.count(), "voluntarios": voluntarios_from_disp(disp_saude_ok)},
        "nao_ok": {"total": disp_saude_nao_ok.count(), "voluntarios": voluntarios_from_disp(disp_saude_nao_ok)},
        "nao_resp": {"total": disp_saude_nao_resp.count(), "voluntarios": voluntarios_from_disp(disp_saude_nao_resp)},
    }

    # ====== 5) Alimentação ======
    por_alimentacao_qs = (
        disp_qs.values("voluntario__alimentacao")
        .annotate(total=Count("id"))
    )
    por_alimentacao_map = {r["voluntario__alimentacao"]: r["total"] for r in por_alimentacao_qs}

    alimentacao_lista = []
    for key, nome in TIPO_ALIMENTACAO:
        alimentacao_lista.append({
            "key": key,
            "nome": nome,
            "total": por_alimentacao_map.get(key, 0),
        })
    alimentacao_nao_preenchido = por_alimentacao_map.get(None, 0)

    # ====== 6) Talentos dos ajudantes (com nomes) ======
    # Pega voluntários que podem ajudar (ajudantes) + seus talentos
    voluntarios_ajudantes = (
        Voluntario.objects.ativos()
        .filter(
            disponibilidades__sabado=sabado,
            disponibilidades__vai_ao_projeto=True,
            disponibilidades__pode_ajudar__isnull=False,
        )
        .distinct()
        .prefetch_related("talentos")
    )

    talentos_map = defaultdict(list)  # "Talento X" -> [Voluntario, ...]
    for v in voluntarios_ajudantes:
        for t in v.talentos.all():
            talentos_map[str(t)].append(v)

    talentos_cards = []
    for nome_talento, vols in talentos_map.items():
        vols_sorted = sorted(vols, key=lambda v: (v.get_full_name() or v.username).lower())
        talentos_cards.append({
            "talento": nome_talento,
            "total": len(vols_sorted),
            "voluntarios": vols_sorted,
        })
    talentos_cards.sort(key=lambda x: x["total"], reverse=True)

    AREAS_SAUDE_RESTRITA = {"TRIADE", "GESTAO_DE_TALENTOS"}
    pode_ver_saude_nao_ok = (
        request.user.is_superuser
        or request.user.is_staff
        or getattr(request.user, "area", None) in AREAS_SAUDE_RESTRITA
    )

    # Quem NÃO VAI é diferente de quem não respondeu: o primeiro se posicionou,
    # muitas vezes por um motivo pessoal. Só Tríade e Gestão de Talentos veem os
    # nomes; para o resto fica o número, que é o que serve para planejar o dia.
    pode_ver_quem_nao_vai = pode_ver_saude_nao_ok

    voluntarios_nao_vao = (
        sorted((d.voluntario for d in disp_nao_vao),
               key=lambda v: (v.get_full_name() or v.username).lower())
        if pode_ver_quem_nao_vai else []
    )

    context = {
        "sabados": sabados,
        "sabado": sabado,
        "total_nao_responderam": total_nao_responderam,
        "nao_responderam_por_area": nao_responderam_por_area,
        "total_ativos": total_ativos,
        "total_responderam": total_responderam,
        "percentual_resposta": percentual_resposta,
        "total_nao_vao": total_nao_vao,
        "voluntarios_nao_vao": voluntarios_nao_vao,
        "pode_ver_quem_nao_vai": pode_ver_quem_nao_vai,
        "total_voluntarios": total_voluntarios,
        "total_ajudantes": total_ajudantes,
        "por_area_lista": por_area_lista,
        "faixa_cards": faixa_cards,
        "total_carro": total_carro,
        "total_nao_carro": total_nao_carro,
        "total_carro_nao_resp": total_carro_nao_resp,
        "saude": saude,
        "alimentacao_lista": alimentacao_lista,
        "alimentacao_nao_preenchido": alimentacao_nao_preenchido,
        "talentos_cards": talentos_cards,
        "pode_ver_saude_nao_ok": pode_ver_saude_nao_ok,
    }
    return render(request, "resumo_sabado.html", context)