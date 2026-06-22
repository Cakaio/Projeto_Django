from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views.generic import FormView, ListView, TemplateView
from django.urls import reverse_lazy
from .models import FeedbackArea
from .forms import FeedbackAreaForm

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
