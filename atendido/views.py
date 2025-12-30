from django.views.generic import ListView, DetailView
from .models import Atendido

LISTA_SALAS = [
    ("VIOLETA", "Violeta"),
    ("ANIL", "Anil"),
    ("AZUL", "Azul"),
    ("VERDE", "Verde"),
    ("AMARELO", "Amarelo"),
    ("LARANJA", "Laranja"),
    ("VERMELHO", "Vermelho"),
    ("FAMILIA_FELIZ", "Família Feliz"),
]

class Homepage(ListView):
    model = Atendido
    template_name = 'homepage.html'
    context_object_name = 'atendidos'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["salas"] = LISTA_SALAS
        return context


class DetalheAtendido(DetailView):
    model = Atendido
    template_name = 'detalhe_atendido.html'
