from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views import View
from django.views.generic import FormView, ListView, TemplateView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from .models import FeedbackArea, PedidoReembolso, ReceptorNotificacaoReembolso
from .forms import FeedbackAreaForm, PedidoReembolsoForm
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


class AprovarReembolsoView(LoginRequiredMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (request.user.is_superuser or getattr(request.user, 'area', None) in REEMBOLSO_AREAS):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        pedido = get_object_or_404(PedidoReembolso, pk=pk, status='PENDENTE')
        lan = Lancamento.objects.create(
            categoria=pedido.categoria,
            valor=pedido.valor,
            data=timezone.now().date(),
            descricao=f'Reembolso: {pedido.descricao}',
            origem='REEMBOLSO',
            criado_por=request.user,
        )
        pedido.status = 'APROVADO'
        pedido.aprovado_por = request.user
        pedido.aprovado_em = timezone.now()
        pedido.lancamento = lan
        pedido.save()
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
            return redirect('forms_pcf:reembolso_inbox')
        pedido.status = 'REJEITADO'
        pedido.observacao_adm = motivo
        pedido.aprovado_por = request.user
        pedido.aprovado_em = timezone.now()
        pedido.save()
        return redirect('forms_pcf:reembolso_inbox')
