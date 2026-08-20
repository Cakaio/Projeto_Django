from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count, Sum
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.apps import apps
from functools import wraps
from decimal import Decimal
from datetime import date
import csv
from .models import (
    Categoria, Conta, Lancamento, RecargaCartao, TetoArea, ORIGENS_AUTOMATICAS,
)
from .forms import CategoriaForm, ContaForm, LancamentoForm, RecargaCartaoForm, TetoAreaForm
from .servicos import (despesas_por_categoria, limites_do_semestre,
                       rotulo_do_semestre, saldo_das_contas, situacao_dos_tetos)
from forms_pcf.forms import PagamentoReembolsoForm
from forms_pcf.views import sincronizar_lancamento_do_reembolso

AREAS_LEITURA = {'ADM/FIN', 'TRIADE'}
AREAS_ESCRITA = {'ADM/FIN'}

# Prestação de contas é a única tela do Financeiro que o CR/RE enxerga: ele
# precisa dela para responder ao doador, mas continua fora dos lançamentos.
AREAS_PRESTACAO_CONTAS = {'ADM/FIN', 'TRIADE', 'CR/RE'}


class AdmAcessoMixin(LoginRequiredMixin):
    """Leitura: ADM/FIN, TRIADE, superuser."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_LEITURA):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AdmEscritaMixin(LoginRequiredMixin):
    """Escrita: ADM/FIN, superuser."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_ESCRITA):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def adm_acesso_required(view_func):
    """Decorator para function-based views de leitura ADM."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_LEITURA):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def adm_escrita_required(view_func):
    """Decorator para function-based views de escrita ADM."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in AREAS_ESCRITA):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


@adm_acesso_required
def painel(request):
    total_receitas = Lancamento.objects.filter(tipo='RECEITA').aggregate(t=Sum('valor'))['t'] or Decimal('0')
    total_despesas = Lancamento.objects.filter(tipo='DESPESA').aggregate(t=Sum('valor'))['t'] or Decimal('0')
    saldo = total_receitas - total_despesas
    ultimos = Lancamento.objects.select_related('categoria').order_by('-data', '-criado_em')[:10]
    PedidoReembolso = apps.get_model('forms_pcf', 'PedidoReembolso')
    reembolsos_pendentes = PedidoReembolso.objects.filter(status='PENDENTE').count()

    return render(request, 'painel_adm.html', {
        'saldo': saldo,
        'total_receitas': total_receitas,
        'total_despesas': total_despesas,
        'ultimos': ultimos,
        'reembolsos_pendentes': reembolsos_pendentes,
    })


@adm_acesso_required
def lista_lancamentos(request):
    qs = Lancamento.objects.select_related('categoria', 'criado_por').all()

    tipo = request.GET.get('tipo')
    categoria_id = request.GET.get('categoria')
    mes = request.GET.get('mes')   # formato YYYY-MM

    if tipo in ('RECEITA', 'DESPESA'):
        qs = qs.filter(tipo=tipo)
    if categoria_id:
        qs = qs.filter(categoria_id=categoria_id)
    if mes:
        try:
            ano, m = mes.split('-')
            qs = qs.filter(data__year=ano, data__month=m)
        except ValueError:
            pass

    categorias = Categoria.objects.filter(ativo=True)
    return render(request, 'lista_lancamentos.html', {
        'lancamentos': qs,
        'categorias': categorias,
        'filtro_tipo': tipo,
        'filtro_categoria': categoria_id,
        'filtro_mes': mes,
    })


@adm_escrita_required
def criar_lancamento(request):
    form = LancamentoForm(request.POST or None)
    if form.is_valid():
        lan = form.save(commit=False)
        lan.origem = 'MANUAL'
        lan.criado_por = request.user
        lan.save()
        messages.success(request, 'Lançamento registrado!')
        return redirect('adm:lista_lancamentos')
    return render(request, 'form_lancamento.html', {'form': form, 'titulo': 'Novo Lançamento'})


@adm_escrita_required
def editar_lancamento(request, pk):
    lan = get_object_or_404(Lancamento, pk=pk)
    if lan.origem in ORIGENS_AUTOMATICAS:
        messages.error(
            request,
            f'Lançamentos com origem "{lan.get_origem_display()}" são gerados automaticamente '
            'e não podem ser editados aqui. Altere o registro de origem.'
        )
        return redirect('adm:lista_lancamentos')
    form = LancamentoForm(request.POST or None, instance=lan)
    if form.is_valid():
        form.save()
        messages.success(request, 'Lançamento atualizado!')
        return redirect('adm:lista_lancamentos')
    return render(request, 'form_lancamento.html', {'form': form, 'titulo': 'Editar Lançamento', 'objeto': lan})


@adm_escrita_required
def deletar_lancamento(request, pk):
    lan = get_object_or_404(Lancamento, pk=pk)
    if lan.origem in ORIGENS_AUTOMATICAS:
        messages.error(
            request,
            f'Lançamentos com origem "{lan.get_origem_display()}" são gerados automaticamente '
            'e não podem ser removidos aqui. Remova o registro de origem.'
        )
        return redirect('adm:lista_lancamentos')
    if request.method == 'POST':
        lan.delete()
        messages.success(request, 'Lançamento removido.')
        return redirect('adm:lista_lancamentos')
    return render(request, 'form_lancamento.html', {
        'objeto': lan, 'confirmar_delecao': True, 'titulo': 'Remover Lançamento'
    })


@adm_acesso_required
def lista_categorias(request):
    categorias = Categoria.objects.all()
    return render(request, 'lista_categorias.html', {'categorias': categorias})


@adm_escrita_required
def criar_categoria(request):
    form = CategoriaForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Categoria criada com sucesso!')
        return redirect('adm:lista_categorias')
    return render(request, 'form_categoria.html', {'form': form, 'titulo': 'Nova Categoria'})


@adm_escrita_required
def editar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    form = CategoriaForm(request.POST or None, instance=categoria)
    if form.is_valid():
        form.save()
        messages.success(request, 'Categoria atualizada!')
        return redirect('adm:lista_categorias')
    return render(request, 'form_categoria.html', {'form': form, 'titulo': 'Editar Categoria', 'objeto': categoria})


@adm_escrita_required
def deletar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == 'POST':
        try:
            categoria.delete()
            messages.success(request, 'Categoria removida.')
        except ProtectedError:
            messages.error(request, 'Não é possível remover: existem lançamentos vinculados.')
        return redirect('adm:lista_categorias')
    return render(request, 'form_categoria.html', {'objeto': categoria, 'confirmar_delecao': True, 'titulo': 'Remover Categoria'})


@adm_acesso_required
def fluxo_caixa(request):
    qs = Lancamento.objects.select_related('categoria').order_by('data', 'criado_em')

    # Filtros
    tipo = request.GET.get('tipo')
    categoria_id = request.GET.get('categoria')
    data_ini = request.GET.get('data_ini')
    data_fim = request.GET.get('data_fim')
    exportar = request.GET.get('exportar')

    if tipo in ('RECEITA', 'DESPESA'):
        qs = qs.filter(tipo=tipo)
    if categoria_id:
        qs = qs.filter(categoria_id=categoria_id)
    if data_ini:
        qs = qs.filter(data__gte=data_ini)
    if data_fim:
        qs = qs.filter(data__lte=data_fim)

    # Calcular saldo acumulado
    saldo = Decimal('0')
    lancamentos_com_saldo = []
    for lan in qs:
        if lan.tipo == 'RECEITA':
            saldo += lan.valor
        else:
            saldo -= lan.valor
        lancamentos_com_saldo.append({'lan': lan, 'saldo': saldo})

    if exportar == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="fluxo_caixa.csv"'
        response.write('﻿')  # BOM para Excel reconhecer UTF-8
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['Data', 'Descrição', 'Categoria', 'Tipo', 'Entrada (R$)', 'Saída (R$)', 'Saldo (R$)'])
        for item in lancamentos_com_saldo:
            lan = item['lan']
            entrada = lan.valor if lan.tipo == 'RECEITA' else ''
            saida = lan.valor if lan.tipo == 'DESPESA' else ''
            writer.writerow([
                lan.data.strftime('%d/%m/%Y'),
                lan.descricao or lan.categoria.nome,
                lan.categoria.nome,
                lan.get_tipo_display(),
                str(entrada).replace('.', ',') if entrada else '',
                str(saida).replace('.', ',') if saida else '',
                str(item['saldo']).replace('.', ','),
            ])
        return response

    categorias = Categoria.objects.filter(ativo=True)
    return render(request, 'fluxo_caixa.html', {
        'lancamentos_com_saldo': lancamentos_com_saldo,
        'saldo_final': saldo,
        'categorias': categorias,
        'filtro_tipo': tipo,
        'filtro_categoria': categoria_id,
        'filtro_data_ini': data_ini,
        'filtro_data_fim': data_fim,
    })


def _calcular_dre(ano, mes):
    """Retorna dict com receitas, despesas e resultado para um mês."""
    qs = Lancamento.objects.filter(data__year=ano, data__month=mes)

    receitas = (
        qs.filter(tipo='RECEITA')
        .values('categoria__nome')
        .annotate(total=Sum('valor'))
        .order_by('categoria__nome')
    )
    despesas = (
        qs.filter(tipo='DESPESA')
        .values('categoria__nome')
        .annotate(total=Sum('valor'))
        .order_by('categoria__nome')
    )

    total_receitas = qs.filter(tipo='RECEITA').aggregate(t=Sum('valor'))['t'] or Decimal('0')
    total_despesas = qs.filter(tipo='DESPESA').aggregate(t=Sum('valor'))['t'] or Decimal('0')

    return {
        'receitas': list(receitas),
        'despesas': list(despesas),
        'total_receitas': total_receitas,
        'total_despesas': total_despesas,
        'resultado': total_receitas - total_despesas,
    }


@adm_acesso_required
def dre(request):
    hoje = timezone.now().date()

    # Período principal
    mes_str = request.GET.get('mes', hoje.strftime('%Y-%m'))
    # Período comparativo
    comp_str = request.GET.get('comparar', '')

    try:
        ano_p, mes_p = [int(x) for x in mes_str.split('-')]
    except (ValueError, AttributeError):
        ano_p, mes_p = hoje.year, hoje.month

    dre_principal = _calcular_dre(ano_p, mes_p)
    dre_comparativo = None
    deltas = None

    if comp_str:
        try:
            ano_c, mes_c = [int(x) for x in comp_str.split('-')]
            dre_comparativo = _calcular_dre(ano_c, mes_c)

            # Construir dicts {categoria_nome: total} para lookup
            rec_p = {r['categoria__nome']: r['total'] for r in dre_principal['receitas']}
            rec_c = {r['categoria__nome']: r['total'] for r in dre_comparativo['receitas']}
            desp_p = {d['categoria__nome']: d['total'] for d in dre_principal['despesas']}
            desp_c = {d['categoria__nome']: d['total'] for d in dre_comparativo['despesas']}

            # Calcular deltas para cada categoria
            deltas = {
                'receitas': {k: rec_p.get(k, Decimal('0')) - rec_c.get(k, Decimal('0'))
                            for k in set(list(rec_p.keys()) + list(rec_c.keys()))},
                'despesas': {k: desp_p.get(k, Decimal('0')) - desp_c.get(k, Decimal('0'))
                            for k in set(list(desp_p.keys()) + list(desp_c.keys()))},
                'resultado': dre_principal['resultado'] - dre_comparativo['resultado'],
            }
        except (ValueError, AttributeError):
            pass

    return render(request, 'dre.html', {
        'dre': dre_principal,
        'dre_comp': dre_comparativo,
        'deltas': deltas,
        'mes': mes_str,
        'comparar': comp_str,
    })


def _data_ou_padrao(texto, padrao):
    """Lê uma data da querystring e cai no padrão se ela não servir.

    parse_date() ainda levanta ValueError quando o formato está certo mas o dia
    não existe ('2026-02-31'), então o try é obrigatório: link torto colado no
    grupo do WhatsApp não pode virar erro 500 na cara do voluntário.
    """
    try:
        return parse_date(texto or '') or padrao
    except ValueError:
        return padrao


def _periodo_prestacao_contas(request):
    """Período do filtro, com o ano corrente como padrão."""
    hoje = timezone.localdate()
    padrao_inicio = date(hoje.year, 1, 1)
    padrao_fim = date(hoje.year, 12, 31)

    inicio = _data_ou_padrao(request.GET.get('inicio'), padrao_inicio)
    fim = _data_ou_padrao(request.GET.get('fim'), padrao_fim)

    # Fim antes do início não é filtro, é erro de digitação: mostrar zero
    # despesas faria o doador achar que o projeto não gastou nada.
    if fim < inicio:
        return padrao_inicio, padrao_fim

    return inicio, fim


@login_required
def onde_investimos(request):
    """Prestação de contas: para onde foi o dinheiro, por categoria.

    Gate escrito à mão de propósito — adm_acesso_required é mais estreito e
    deixaria o CR/RE de fora, e é justamente ele quem precisa desta tela para
    responder ao doador. Somente leitura: nada aqui cria, edita ou apaga
    lançamento.
    """
    if not (request.user.is_superuser
            or getattr(request.user, 'area', None) in AREAS_PRESTACAO_CONTAS):
        raise PermissionDenied('Esta tela é do Financeiro e do CR/RE.')

    inicio, fim = _periodo_prestacao_contas(request)
    linhas, total = despesas_por_categoria(inicio, fim)

    return render(request, 'onde_investimos.html', {
        'linhas': linhas,
        'total': total,
        'quantidade_lancamentos': sum(linha['lancamentos'] for linha in linhas),
        'inicio': inicio,
        'fim': fim,
    })


# ─── Contas, cartões e recargas ───

@adm_acesso_required
def contas(request):
    """Painel das contas: onde o dinheiro está e quanto sobra em cada cartão."""
    saldos = saldo_das_contas()
    return render(request, 'lista_contas.html', {
        'contas': Conta.objects.select_related('responsavel'),
        'saldos': saldos,
        'total_recarregado': sum((linha['recarregado'] for linha in saldos), Decimal('0')),
        'total_gasto': sum((linha['gasto'] for linha in saldos), Decimal('0')),
        'total_saldo': sum((linha['saldo'] for linha in saldos), Decimal('0')),
    })


@adm_escrita_required
def conta_form(request, pk=None):
    conta = get_object_or_404(Conta, pk=pk) if pk else None
    form = ContaForm(request.POST or None, instance=conta)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Conta salva!' if conta else 'Conta cadastrada!')
        return redirect('adm:contas')
    return render(request, 'form_conta.html', {
        'form': form,
        'titulo': 'Editar Conta' if conta else 'Nova Conta',
        'objeto': conta,
    })


@adm_acesso_required
def recargas(request):
    """Histórico de recargas de cartão.

    Recarga não é despesa: nenhuma linha daqui vira lançamento, senão o mesmo
    real apareceria duas vezes no fluxo de caixa — uma na recarga e outra
    quando o cartão fosse usado.
    """
    lista = RecargaCartao.objects.select_related('conta', 'carregado_por')

    conta_id = request.GET.get('conta')
    if conta_id:
        lista = lista.filter(conta_id=conta_id)

    return render(request, 'lista_recargas.html', {
        'recargas': lista,
        'contas': Conta.objects.all(),
        'filtro_conta': conta_id,
        'total': lista.aggregate(t=Sum('valor'))['t'] or Decimal('0'),
    })


@adm_escrita_required
def recarga_form(request, pk=None):
    recarga = get_object_or_404(RecargaCartao, pk=pk) if pk else None
    form = RecargaCartaoForm(request.POST or None, instance=recarga)
    if request.method == 'POST' and form.is_valid():
        nova = form.save(commit=False)
        # Quem está cadastrando é o palpite mais provável de quem carregou —
        # mas se o formulário disse outra pessoa, ela manda.
        if not nova.carregado_por_id:
            nova.carregado_por = request.user
        nova.save()
        messages.success(request, 'Recarga salva!' if recarga else 'Recarga registrada!')
        return redirect('adm:recargas')
    return render(request, 'form_recarga.html', {
        'form': form,
        'titulo': 'Editar Recarga' if recarga else 'Nova Recarga',
        'objeto': recarga,
    })


# ─── Tetos por área ───

def _semestre_escolhido(bruto):
    """Lê ?semestre=YYYY-N da querystring. Valor torto cai no semestre atual —
    filtro que não dá para entender não derruba a página."""
    hoje = timezone.localdate()
    if not bruto:
        return hoje
    try:
        ano, numero = bruto.split('-')
        ano, numero = int(ano), int(numero)
    except (ValueError, TypeError):
        return hoje
    if numero not in (1, 2) or not (2000 <= ano <= 2100):
        return hoje
    return date(ano, 1 if numero == 1 else 7, 1)


def _semestres_para_escolher(quantos=6):
    """Os últimos semestres, do mais recente para o mais antigo.

    Lista fechada em vez de campo de data livre: semestre não é data, e um
    seletor de mês faria o usuário achar que o teto é mensal.
    """
    hoje = timezone.localdate()
    ano, numero = hoje.year, 1 if hoje.month <= 6 else 2
    opcoes = []
    for _ in range(quantos):
        opcoes.append({'valor': f'{ano}-{numero}', 'rotulo': f'{numero}º semestre de {ano}'})
        numero -= 1
        if numero == 0:
            numero, ano = 2, ano - 1
    return opcoes


@login_required
def tetos(request):
    """Teto x gasto de cada área no semestre.

    Gate escrito à mão de propósito: é a única tela do Financeiro aberta a
    qualquer voluntário logado, porque o pedido é que cada um veja a situação
    do teto da sua área sem depender do ADM. Somente leitura, e só teto x
    gasto — nenhum lançamento individual aparece aqui.

    O teto é um só por área e vale até alguém alterar; o que muda de período é
    o gasto, medido no semestre escolhido.
    """
    referencia = _semestre_escolhido(request.GET.get('semestre'))
    inicio, fim = limites_do_semestre(referencia)
    linhas = situacao_dos_tetos(referencia)

    area_do_usuario = getattr(request.user, 'area', '') or ''
    minha_linha = next((linha for linha in linhas if linha['area'] == area_do_usuario), None)

    return render(request, 'tetos.html', {
        'linhas': linhas,
        'referencia': referencia,
        'semestre_rotulo': rotulo_do_semestre(referencia),
        'semestre': f'{referencia.year}-{1 if referencia.month <= 6 else 2}',
        'semestres': _semestres_para_escolher(),
        'inicio': inicio,
        'fim': fim,
        'minha_linha': minha_linha,
        'area_do_usuario': area_do_usuario,
        'total_teto': sum((linha['teto'] for linha in linhas if linha['teto'] is not None), Decimal('0')),
        'total_gasto': sum((linha['gasto'] for linha in linhas), Decimal('0')),
        'estouros': sum(1 for linha in linhas if linha['estourou']),
        'gastos_sem_teto': sum(1 for linha in linhas if linha['sem_teto']),
        # A tela é de leitura para todos; o botão de editar só faz sentido para
        # quem tem escrita no Financeiro.
        'pode_editar': (request.user.is_superuser
                        or getattr(request.user, 'area', None) in AREAS_ESCRITA),
    })


@adm_escrita_required
def teto_form(request, pk=None):
    teto = get_object_or_404(TetoArea, pk=pk) if pk else None
    form = TetoAreaForm(request.POST or None, instance=teto)
    if request.method == 'POST' and form.is_valid():
        novo = form.save(commit=False)
        novo.definido_por = request.user
        novo.save()
        messages.success(request, 'Teto salvo!' if teto else 'Teto definido!')
        return redirect('adm:tetos')
    return render(request, 'form_teto.html', {
        'form': form,
        'titulo': 'Editar Teto' if teto else 'Novo Teto',
        'objeto': teto,
    })


# ─── Reembolsos pagos ───

STATUS_REEMBOLSO_PAINEL = ('APROVADO', 'PAGO', 'PENDENTE', 'REJEITADO')


@adm_acesso_required
def reembolsos(request):
    """Painel dos reembolsos: quem já foi pago e quem está esperando dinheiro."""
    PedidoReembolso = apps.get_model('forms_pcf', 'PedidoReembolso')

    status = request.GET.get('status', 'APROVADO')
    if status not in STATUS_REEMBOLSO_PAINEL:
        status = 'APROVADO'

    pedidos = (PedidoReembolso.objects
               .filter(status=status)
               .select_related('solicitante', 'categoria', 'conta_pagamento',
                               'evento', 'pago_por', 'aprovado_por'))

    # Uma consulta para todas as contagens, em vez de um count() por status.
    contagens = {
        linha['status']: linha['quantidade']
        for linha in PedidoReembolso.objects.values('status').annotate(quantidade=Count('id'))
    }

    return render(request, 'lista_reembolsos.html', {
        'pedidos': pedidos,
        'status_ativo': status,
        'contagem_aprovado': contagens.get('APROVADO', 0),
        'contagem_pago': contagens.get('PAGO', 0),
        'contagem_pendente': contagens.get('PENDENTE', 0),
        'contagem_rejeitado': contagens.get('REJEITADO', 0),
        'total_do_filtro': pedidos.aggregate(t=Sum('valor'))['t'] or Decimal('0'),
        'total_a_pagar': (PedidoReembolso.objects.filter(status='APROVADO')
                          .aggregate(t=Sum('valor'))['t'] or Decimal('0')),
    })


def _avisar_solicitante_do_pagamento(pedido):
    """E-mail de confirmação para quem pediu o reembolso.

    Devolve o endereço usado, ou '' se o solicitante não tem e-mail. Não engole
    falha de envio: quem chama precisa saber para avisar na tela — mas sem
    desfazer o pagamento, que já aconteceu no banco de verdade.
    """
    destino = (getattr(pedido.solicitante, 'email', '') or '').strip()
    if not destino:
        return ''

    conta = pedido.conta_pagamento.nome if pedido.conta_pagamento else 'não informada'
    data_pagamento = pedido.pago_em or timezone.localdate()
    corpo = (
        'Olá!\n\n'
        'Seu reembolso foi pago.\n\n'
        f'Valor: R$ {pedido.valor}\n'
        f'Data do pagamento: {data_pagamento:%d/%m/%Y}\n'
        f'Conta usada: {conta}\n'
        f'Referente a: {pedido.descricao}\n\n'
        'Se o valor não tiver caído, fale com a ADM/Fin.\n\n'
        'Projeto Criança Feliz'
    )
    send_mail(
        f'[PCF] Reembolso pago — R$ {pedido.valor}',
        corpo,
        settings.DEFAULT_FROM_EMAIL,
        [destino],
        fail_silently=False,   # falha precisa virar aviso na tela, não silêncio
    )
    return destino


@adm_escrita_required
def reembolso_pagar(request, pk):
    """Marca o reembolso como PAGO: comprovante, conta, quem pagou e quando."""
    PedidoReembolso = apps.get_model('forms_pcf', 'PedidoReembolso')
    pedido = get_object_or_404(
        PedidoReembolso.objects.select_related('solicitante', 'categoria', 'lancamento'),
        pk=pk,
    )

    if pedido.status != 'APROVADO':
        # PENDENTE ainda não foi decidido; PAGO já saiu do caixa, e pagar de
        # novo geraria despesa em dobro.
        messages.error(
            request,
            'Só reembolso aprovado pode ser marcado como pago. '
            f'Este está como "{pedido.get_status_display()}".'
        )
        return redirect('adm:reembolsos')

    form = PagamentoReembolsoForm(request.POST or None, request.FILES or None, instance=pedido)

    if request.method == 'POST' and form.is_valid():
        pago = form.save(commit=False)
        pago.status = 'PAGO'
        pago.pago_por = request.user
        pago.pago_em = pago.pago_em or timezone.localdate()
        # O lançamento leva área, evento e conta do pedido: sem isso o gasto
        # não conta no teto da área nem no evento.
        sincronizar_lancamento_do_reembolso(pago, request.user)
        pago.save()
        messages.success(request, 'Reembolso marcado como pago.')

        # O dinheiro já saiu: nenhum problema de e-mail pode desfazer isso. Por
        # isso o except é largo — SMTP fora do ar, DNS, credencial expirada.
        try:
            destino = _avisar_solicitante_do_pagamento(pago)
        except Exception as erro:
            messages.warning(
                request,
                'Pagamento registrado, mas o e-mail de confirmação não saiu '
                f'({erro}). Avise o solicitante por outro caminho.'
            )
        else:
            if destino:
                messages.info(request, f'Confirmação enviada para {destino}.')
            else:
                messages.warning(
                    request,
                    'Pagamento registrado, mas o solicitante não tem e-mail '
                    'cadastrado — avise por outro caminho.'
                )
        return redirect('adm:reembolsos')

    return render(request, 'form_reembolso_pagar.html', {
        'form': form,
        'pedido': pedido,
        'titulo': 'Registrar Pagamento',
    })
