from django.shortcuts import render
from .models import Atendido
from django.views.generic import ListView, DetailView

#def homepage(request):
 #   atendidos = Atendido.objects.all()
  #  return render(request, 'homepage.html', {'variavel_atendidos': atendidos})

class Homepage(ListView):
    model = Atendido
    template_name = 'homepage.html'
    #object_list é a lista de itens do modelo

class DetalheAtendido(DetailView):
    model = Atendido
    template_name = 'detalhe_atendido.html'
    #object é um item do modelo