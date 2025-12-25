from django.shortcuts import render

def homepage_inicial(request):
    return render(request, 'homepage_inicial.html')
