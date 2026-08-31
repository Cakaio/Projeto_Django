from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views import View
from django.views.generic import FormView, ListView, TemplateView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.core.mail import send_mail
from django.contrib import messages
from django.utils import timezone
from functools import wraps
from .models import FeedbackArea, PedidoReembolso, ReceptorNotificacaoReembolso
from .forms import FeedbackAreaForm, PedidoReembolsoForm, ReceptorNotificacaoReembolsoForm
from adm.models import Lancamento

FEEDBACK_AREAS = {'PROJETOS', 'TRIADE'}


class EnviarFeedbackView(LoginRequiredMixin, FormView):
    template_name = 'feedback_form.html'
    form_class = FeedbackAreaForm
    success_url = reverse_lazy('forms_pcf:feedback_sucesso')

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


class FeedbackSucessoView(LoginRequiredMixin, TemplateView):
    template_name = 'feedback_sucesso.html'


class FeedbackInboxView(LoginRequiredMixin, ListView):
    template_name = 'feedback_inbox.html'
    context_object_name = 'feedbacks'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in FEEDBACK_AREAS):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return FeedbackArea.objects.order_by('-criado_em')


REEMBOLSO_AREAS = {'ADM/FIN'}


def sincronizar_lancamento_do_reembolso(pedido, usuario=None):
    """Garante o lançamento de despesa do reembolso carregando área, evento e
    conta do pedido.

    Sem esses três o gasto do reembolso não entra no teto da área nem no
    evento — e contabilizar no teto era metade do que a ADM pediu. Vive aqui,
    e não na view de pagamento, porque aprovação e pagamento precisam do mesmo
    lançamento: duplicar a regra deixaria os dois lados divergirem.

    Não grava o pedido: quem chama salva, para que criação do lançamento e
    mudança de status caiam juntas.
    """
    if pedido.lancamento_id:
        lancamento = pedido.lancamento
        lancamento.area = pedido.area
        lancamento.evento = pedido.evento
        lancamento.conta = pedido.conta_pagamento
        lancamento.save()
        return lancamento

    lancamento = Lancamento.objects.create(
        categoria=pedido.categoria,
        valor=pedido.valor,
        data=timezone.now().date(),
        descricao=f'Reembolso: {pedido.descricao}',
        origem='REEMBOLSO',
        criado_por=usuario,
        area=pedido.area,
        evento=pedido.evento,
        conta=pedido.conta_pagamento,
    )
    pedido.lancamento = lancamento
    return lancamento


class EnviarReembolsoView(LoginRequiredMixin, FormView):
    template_name = 'reembolso_form.html'
    form_class = PedidoReembolsoForm
    success_url = reverse_lazy('forms_pcf:reembolso_sucesso')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['files'] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        pedido = form.save(commit=False)
        pedido.solicitante = self.request.user
        # A área sai de quem está pedindo — o formulário não pergunta de
        # propósito. Sem isso o pedido chegava na fila da ADM como "sem área
        # nem evento", e o gasto só era atribuído no momento do pagamento: até
        # lá ninguém sabia de qual teto aquele dinheiro ia sair. A ADM continua
        # podendo trocar na hora de pagar, que é quando se sabe se o gasto era
        # de um evento e não da área da pessoa.
        pedido.area = getattr(self.request.user, 'area', '') or ''
        pedido.status = 'PENDENTE'
        pedido.save()
        self._enviar_email(pedido)
        return super().form_valid(form)

    def _enviar_email(self, pedido):
        receptores = list(
            ReceptorNotificacaoReembolso.objects.filter(ativo=True).values_list('email', flat=True)
        )
        if not receptores:
            return
        nome = pedido.solicitante.get_full_name() or pedido.solicitante.username
        area = getattr(pedido.solicitante, 'area', '—')
        assunto = f'[PCF] Novo pedido de reembolso — R$ {pedido.valor}'
        corpo = (
            f'Novo pedido de reembolso recebido.\n\n'
            f'Solicitante: {nome}\n'
            f'Área: {area}\n'
            f'Valor: R$ {pedido.valor}\n'
            f'Data do gasto: {pedido.data_gasto:%d/%m/%Y}\n'
            f'Categoria: {pedido.categoria.nome}\n'
            f'Descrição: {pedido.descricao}\n\n'
            f'Acesse o sistema para aprovar ou rejeitar.'
        )
        send_mail(assunto, corpo, settings.DEFAULT_FROM_EMAIL, receptores, fail_silently=True)


class ReembolsoSucessoView(LoginRequiredMixin, TemplateView):
    template_name = 'reembolso_sucesso.html'


class ReembolsoInboxView(LoginRequiredMixin, ListView):
    template_name = 'reembolso_inbox.html'
    context_object_name = 'pedidos'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in REEMBOLSO_AREAS):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        status = self.request.GET.get('status', 'PENDENTE')
        if status not in ('PENDENTE', 'APROVADO', 'REJEITADO'):
            status = 'PENDENTE'
        return PedidoReembolso.objects.filter(status=status).select_related(
            'solicitante', 'categoria', 'aprovado_por'
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_ativo'] = self.request.GET.get('status', 'PENDENTE')
        ctx['contagem_pendente'] = PedidoReembolso.objects.filter(status='PENDENTE').count()
        ctx['contagem_aprovado'] = PedidoReembolso.objects.filter(status='APROVADO').count()
        ctx['contagem_rejeitado'] = PedidoReembolso.objects.filter(status='REJEITADO').count()
        return ctx


def avisar_solicitante_da_aprovacao(pedido):
    """E-mail para quem pediu, no momento em que a ADM aprova.

    Antes o solicitante não recebia nada na aprovação: descobria pelo e-mail de
    pagamento, que pode vir dias depois, ou não descobria.

    Aprovado não é pago, e o texto insiste nisso — quem lê "aprovado" e entende
    "o dinheiro caiu" vai cobrar a ADM por um pagamento que ninguém prometeu
    para hoje.

    Devolve o endereço usado, ou '' se a pessoa não tem e-mail cadastrado. Não
    engole falha de envio: quem chama precisa avisar na tela, sem desfazer a
    aprovação, que já está gravada.
    """
    destino = (getattr(pedido.solicitante, 'email', '') or '').strip()
    if not destino:
        return ''

    corpo = (
        'Olá!\n\n'
        'Seu pedido de reembolso foi aprovado pela ADM/Fin.\n\n'
        f'Valor: R$ {pedido.valor}\n'
        f'Referente a: {pedido.descricao}\n'
        f'Data do gasto: {pedido.data_gasto:%d/%m/%Y}\n\n'
        'O pagamento ainda vai ser feito — quando o dinheiro sair, você recebe '
        'outro e-mail com a data e a conta usada.\n\n'
        'Projeto Criança Feliz'
    )
    send_mail(
        f'[PCF] Reembolso aprovado — R$ {pedido.valor}',
        corpo,
        settings.DEFAULT_FROM_EMAIL,
        [destino],
        fail_silently=False,   # falha vira aviso na tela, não silêncio
    )
    return destino


class AprovarReembolsoView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in REEMBOLSO_AREAS):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        pedido = get_object_or_404(PedidoReembolso, pk=pk, status='PENDENTE')
        sincronizar_lancamento_do_reembolso(pedido, request.user)
        pedido.status = 'APROVADO'
        pedido.aprovado_por = request.user
        pedido.aprovado_em = timezone.now()
        pedido.save()
        messages.success(request, 'Reembolso aprovado.')

        # A aprovação já está no banco: nenhum problema de e-mail pode desfazê-la.
        # Por isso o except é largo — SMTP fora do ar, DNS, credencial expirada.
        try:
            destino = avisar_solicitante_da_aprovacao(pedido)
        except Exception as erro:
            messages.warning(
                request,
                'Reembolso aprovado, mas o e-mail de aviso não saiu '
                f'({erro}). Avise o solicitante por outro caminho.'
            )
        else:
            if destino:
                messages.info(request, f'Aviso de aprovação enviado para {destino}.')
            else:
                messages.warning(
                    request,
                    'Reembolso aprovado, mas o solicitante não tem e-mail '
                    'cadastrado — avise por outro caminho.'
                )
        return redirect('forms_pcf:reembolso_inbox')


class RejeitarReembolsoView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in REEMBOLSO_AREAS):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        pedido = get_object_or_404(PedidoReembolso, pk=pk, status='PENDENTE')
        motivo = request.POST.get('observacao_adm', '').strip()
        if not motivo:
            messages.error(request, 'O motivo da rejeição é obrigatório.')
            return redirect('forms_pcf:reembolso_inbox')
        pedido.status = 'REJEITADO'
        pedido.observacao_adm = motivo
        pedido.aprovado_por = request.user
        pedido.aprovado_em = timezone.now()
        pedido.save()
        return redirect('forms_pcf:reembolso_inbox')


def _adm_escrita_required(view_func):
    """Decorator para function-based views de escrita ADM (receptor management)."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in {'ADM/FIN'}):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


@_adm_escrita_required
def receptores_reembolso(request):
    receptores = ReceptorNotificacaoReembolso.objects.all()
    return render(request, 'receptores_reembolso.html', {'receptores': receptores})


@_adm_escrita_required
def receptor_criar(request):
    form = ReceptorNotificacaoReembolsoForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, 'Receptor adicionado!')
        return redirect('adm:receptores_reembolso')
    return render(request, 'form_receptor.html', {'form': form, 'titulo': 'Novo Receptor'})


@_adm_escrita_required
def receptor_editar(request, pk):
    receptor = get_object_or_404(ReceptorNotificacaoReembolso, pk=pk)
    form = ReceptorNotificacaoReembolsoForm(request.POST or None, instance=receptor)
    if form.is_valid():
        form.save()
        messages.success(request, 'Receptor atualizado!')
        return redirect('adm:receptores_reembolso')
    return render(request, 'form_receptor.html', {'form': form, 'titulo': 'Editar Receptor', 'objeto': receptor})


@_adm_escrita_required
def receptor_deletar(request, pk):
    receptor = get_object_or_404(ReceptorNotificacaoReembolso, pk=pk)
    if request.method == 'POST':
        receptor.delete()
        messages.success(request, 'Receptor removido.')
        return redirect('adm:receptores_reembolso')
    return render(request, 'form_receptor.html', {
        'objeto': receptor, 'confirmar_delecao': True, 'titulo': 'Remover Receptor'
    })
