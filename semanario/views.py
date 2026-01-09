# semanario/views.py
from django.views.generic.edit import CreateView
from django.contrib import messages
from django.shortcuts import render
from django.urls import reverse_lazy
from .models import Semanario
from .forms import SemanarioForm

class SemanarioCreateView(CreateView):
    model = Semanario
    form_class = SemanarioForm
    template_name = "semanario_novo.html"
    success_url = reverse_lazy('semanario:criar_semanario')

    def form_valid(self, form):
        messages.success(self.request, "✅ Atividade salva com sucesso!")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "⚠️ Erro ao salvar. Verifique os campos.")
        return super().form_invalid(form)
