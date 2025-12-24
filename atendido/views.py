from django.shortcuts import render
from .models import Atendido

def homepage(request):
    atendidos = Atendido.objects.all()
    return render(request, 'homepage.html', {'atendidos': atendidos})
