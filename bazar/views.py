"""Telas do Bazar.

Três públicos, três telas:

  ATENDIMENTO  — o voluntário de conferência, com fila na frente. É a tela que
                 mais importa e a que menos pode ter clique.
  CONFIGURAÇÃO — a coordenação, antes do evento: cota, categorias, estoque,
                 e a chave que abre e fecha cada etapa.
  PAINEL       — os números do dia, para quem está coordenando.

As views só perguntam; quem decide é `bazar/regras.py`.
"""
import csv
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from atendido.models import Atendido

from .models import Bazar, Categoria, ItemRetirada, Retirada, SalaDoBazar
from .regras import (MINUTOS_PARA_DESFAZER, RetiradaInvalida,
                     cancelar_retirada, finalizar_retirada, numeros_do_bazar,
                     por_salinha, recado_de_ja_retirou, situacao_do_atendido)

# Quem configura e coordena o Bazar. Conferir na fila é outra coisa: qualquer
# voluntário logado pode, porque são eles que estão escalados no dia.
AREAS_DE_COORDENACAO = {"TRIADE", "EVENTOS"}

# Quantos nomes a busca devolve. Lista longa numa fila atrapalha mais que ajuda:
# se vier muita coisa, o certo é digitar mais uma letra.
LIMITE_DA_BUSCA = 8


def idade_de(atendido):
    """Idade em anos, ou None quando a ficha não tem data de nascimento.

    Existe para a busca separar homônimos: sem ela, duas "Maria Eduarda" do
    Amarelo são duas linhas idênticas na lista e o voluntário escolhe no chute.
    Errar aqui é o único erro sem conserto fácil do sistema, porque a trava da
    etapa depois barra a criança certa.
    """
    nascimento = getattr(atendido, "data_nascimento", None)
    if not nascimento:
        return None
    hoje = timezone.localdate()
    return hoje.year - nascimento.year - (
        (hoje.month, hoje.day) < (nascimento.month, nascimento.day))


def coordenacao_required(view):
    @wraps(view)
    @login_required(login_url="/login/")
    def wrapper(request, *args, **kwargs):
        if not pode_coordenar(request.user):
            raise PermissionDenied("Só a Tríade e a área de Eventos configuram o Bazar.")
        return view(request, *args, **kwargs)
    return wrapper


def pode_coordenar(usuario):
    return bool(
        usuario.is_superuser
        or getattr(usuario, "area", None) in AREAS_DE_COORDENACAO
    )


# ────────────────────────────── Atendimento ──────────────────────────────
@login_required(login_url="/login/")
def atendimento(request):
    """A tela da fila: buscar, ver saldo, marcar peças, finalizar."""
    bazar = Bazar.em_andamento()
    return render(request, "bazar/atendimento.html", {
        "bazar": bazar,
        "categorias": (
            Categoria.objects.filter(bazar=bazar, ativo=True) if bazar else []
        ),
        "salas": (
            SalaDoBazar.objects.filter(bazar=bazar, ativo=True) if bazar else []
        ),
        "pode_coordenar": pode_coordenar(request.user),
        "opcoes_retirado_por": Retirada.RetiradoPor.choices,
        "minutos_para_desfazer": MINUTOS_PARA_DESFAZER,
    })


@login_required(login_url="/login/")
def buscar_atendido(request):
    """Busca por nome enquanto o voluntário digita.

    Só nome: na fila ninguém tem o número da matrícula na mão, e pedir mais de
    um campo é mais um motivo para a fila parar.
    """
    bazar = Bazar.em_andamento()
    if bazar is None:
        return JsonResponse({"erro": "Nenhum Bazar aberto."}, status=409)

    termo = (request.GET.get("q") or "").strip()
    if len(termo) < 2:
        return JsonResponse({"resultados": []})

    encontrados = (
        Atendido.objects.ativos()
        .filter(nome__icontains=termo)
        .order_by("nome")[:LIMITE_DA_BUSCA]
    )

    return JsonResponse({"resultados": [
        {
            "id": atendido.pk,
            "nome": atendido.nome,
            "sala": atendido.get_sala_display(),
            # Idade e numerações vão JUNTO do nome, e não numa segunda tela: é
            # o que separa homônimo na hora de escolher, e é o dado que mais
            # economiza tempo na fila de um bazar de roupa.
            "idade": idade_de(atendido),
            "numeracoes": {
                "camisa": atendido.numeracao_camisa or "",
                "calca": atendido.numeracao_calca or "",
                "calcado": atendido.numeracao_calcado or "",
            },
        }
        for atendido in encontrados
    ]})


@login_required(login_url="/login/")
def situacao(request, pk):
    """Tudo sobre a pessoa escolhida: saldo, se já passou, histórico, tamanhos."""
    bazar = Bazar.em_andamento()
    if bazar is None:
        return JsonResponse({"erro": "Nenhum Bazar aberto."}, status=409)

    atendido = get_object_or_404(Atendido, pk=pk, ativo=True)
    dados = situacao_do_atendido(bazar, atendido)

    return JsonResponse({
        "id": atendido.pk,
        "nome": atendido.nome,
        "sala": atendido.get_sala_display(),
        "idade": idade_de(atendido),
        # A frase inteira de quem já passou: hora, sala e quem conferiu. "Já
        # passou" sozinho não diz a quem perguntar, que é o que o voluntário
        # precisa saber com a roupa na mão.
        "recado_ja_retirou": (
            recado_de_ja_retirou(bazar, atendido) if dados["ja_retirou"] else ""
        ),
        "saldo": dados["saldo"],
        "cota": dados["cota"],
        "ja_retirou": dados["ja_retirou"],
        "etapa": bazar.get_etapa_display(),
        "desconta_pontos": bazar.desconta_pontos,
        "numeracoes": dados["numeracoes"],
        "historico": [
            {
                "etapa": retirada.get_etapa_display(),
                "quando": timezone.localtime(retirada.finalizada_em).strftime("%H:%M"),
                "pontos": retirada.pontos_usados,
                "itens": [
                    f"{item.categoria.nome} × {item.quantidade}"
                    for item in retirada.itens.all()
                ],
            }
            for retirada in dados["historico"]
        ],
    })


@login_required(login_url="/login/")
@require_POST
def finalizar(request):
    """Grava a retirada. É o único ponto que escreve durante o evento."""
    bazar = Bazar.em_andamento()
    if bazar is None:
        return JsonResponse({"erro": "Nenhum Bazar aberto."}, status=409)

    # Ou a criança tem ficha, ou é visitante. Quem decide é a tela; aqui só se
    # traduz o que veio no POST.
    atendido = None
    if request.POST.get("atendido"):
        atendido = get_object_or_404(
            Atendido, pk=request.POST["atendido"], ativo=True)

    sala = None
    if request.POST.get("sala"):
        sala = SalaDoBazar.objects.filter(
            bazar=bazar, pk=request.POST["sala"]).first()

    pedido = {}
    for chave, valor in request.POST.items():
        if not chave.startswith("qtd_"):
            continue
        try:
            quantidade = int(valor)
        except (TypeError, ValueError):
            continue
        if quantidade > 0:
            pedido[chave[4:]] = quantidade

    try:
        retirada, total, alertas = finalizar_retirada(
            bazar=bazar,
            atendido=atendido,
            pedido=pedido,
            conferido_por=request.user,
            sala=sala,
            retirado_por=request.POST.get("retirado_por")
                         or Retirada.RetiradoPor.ATENDIDO,
            retirado_por_nome=request.POST.get("retirado_por_nome") or "",
            sem_retirada=bool(request.POST.get("sem_retirada")),
            visitante_nome=request.POST.get("visitante_nome") or "",
            visitante_motivo=request.POST.get("visitante_motivo") or "",
            token=request.POST.get("token") or "",
        )
    except RetiradaInvalida as erro:
        # 409 e não 400: não é requisição malformada, é uma regra do Bazar que
        # não permitiu. A tela mostra o texto como está, sem traduzir.
        return JsonResponse({"erro": str(erro)}, status=409)
    except IntegrityError:
        # Duas salas conferindo a mesma criança ao mesmo tempo. A checagem
        # acontece ANTES da gravação, então a corrida existe de verdade — e sem
        # este bloco ela vira 500 no celular, com a sacola já na mão.
        return JsonResponse({"erro": recado_de_ja_retirou(bazar, atendido)},
                            status=409)

    return JsonResponse({
        "ok": True,
        "retirada": retirada.pk,
        "total": total,
        "pecas": retirada.total_pecas,
        "alertas": alertas,
        "nome": retirada.nome_de_quem_levou,
        "sem_retirada": retirada.sem_retirada,
        "minutos_para_desfazer": MINUTOS_PARA_DESFAZER,
    })


@login_required(login_url="/login/")
@require_POST
def cancelar(request, pk):
    """Desfaz uma retirada, devolvendo-a ao rascunho.

    Só POST: desfazer muda estado, e estado não pode mudar porque alguém abriu
    uma URL. Aberto a qualquer voluntário logado de propósito — quem errou está
    no caixa com a fila andando, e mandá-lo procurar a coordenação para corrigir
    um toque é o que faz a correção não acontecer.
    """
    retirada = get_object_or_404(Retirada, pk=pk)

    try:
        cancelar_retirada(retirada, request.user,
                          request.POST.get("motivo") or "")
    except RetiradaInvalida as erro:
        return JsonResponse({"erro": str(erro)}, status=409)

    return JsonResponse({"ok": True, "retirada": retirada.pk})


# ────────────────────────────── Coordenação ──────────────────────────────
@coordenacao_required
def painel(request):
    """Os números do dia e a chave das etapas."""
    bazar = Bazar.em_andamento() or Bazar.objects.first()
    contexto = {"bazar": bazar, "bazares": Bazar.objects.all()[:10]}

    if bazar:
        contexto |= {
            "numeros": numeros_do_bazar(bazar),
            "salinhas": por_salinha(bazar),
            "categorias": Categoria.objects.filter(bazar=bazar),
            "ultimas": (
                Retirada.objects
                .filter(bazar=bazar, finalizada_em__isnull=False)
                .select_related("atendido", "conferido_por")
                .prefetch_related("itens__categoria")[:15]
            ),
            "etapas": Bazar.Etapa.choices,
        }
    return render(request, "bazar/painel.html", contexto)


@coordenacao_required
@require_POST
def mudar_etapa(request, pk):
    """A chave manual.

    Manual de propósito: evento atrasa. Se o relógio virasse sozinho às 11h com
    a fila da primeira etapa ainda andando, o sistema passaria a liberar
    retirada extra para quem nem foi atendido — e ninguém perceberia na hora.
    """
    bazar = get_object_or_404(Bazar, pk=pk)
    nova = request.POST.get("etapa")

    if nova not in dict(Bazar.Etapa.choices):
        messages.error(request, "Etapa inválida.")
        return redirect("bazar:painel")

    if nova in (Bazar.Etapa.PRIMEIRA, Bazar.Etapa.SEGUNDA):
        aberto = Bazar.em_andamento()
        if aberto and aberto.pk != bazar.pk:
            messages.error(
                request,
                f'"{aberto.nome}" está aberto. Encerre antes de abrir outro.')
            return redirect("bazar:painel")

    bazar.etapa = nova
    bazar.save(update_fields=["etapa"])
    messages.success(request, f"Bazar agora em: {bazar.get_etapa_display()}.")
    return redirect("bazar:painel")


@coordenacao_required
def relatorio(request, pk):
    """Exporta o Bazar inteiro em CSV, linha por peça retirada.

    Uma linha por peça, e não por retirada: assim a planilha soma por categoria,
    por salinha ou por etapa sem ninguém precisar desmontar nada.
    """
    bazar = get_object_or_404(Bazar, pk=pk)

    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = (
        f'attachment; filename="bazar-{bazar.data:%Y-%m-%d}.csv"')
    # BOM: sem ele o Excel abre "João" como "JoÃ£o".
    resposta.write("﻿")

    escritor = csv.writer(resposta, delimiter=";")
    escritor.writerow([
        "Atendido", "Salinha", "Etapa", "Categoria", "Quantidade",
        "Pontos unitários", "Pontos total", "Sala do Bazar",
        "Retirado por", "Nome de quem retirou", "Conferido por", "Horário",
    ])

    itens = (
        ItemRetirada.objects
        .filter(retirada__bazar=bazar, retirada__finalizada_em__isnull=False)
        .select_related("retirada__atendido", "retirada__conferido_por", "categoria")
        .order_by("retirada__finalizada_em", "pk")
    )
    for item in itens:
        retirada = item.retirada
        escritor.writerow([
            retirada.atendido.nome,
            retirada.atendido.get_sala_display(),
            retirada.get_etapa_display(),
            item.categoria.nome,
            item.quantidade,
            item.pontos_unitarios,
            item.pontos_total,
            retirada.sala_do_bazar,
            retirada.get_retirado_por_display(),
            retirada.retirado_por_nome,
            retirada.conferido_por.get_full_name() or retirada.conferido_por.username,
            timezone.localtime(retirada.finalizada_em).strftime("%d/%m/%Y %H:%M"),
        ])

    return resposta
