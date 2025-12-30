from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect

def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)  # agora chama o login do Django corretamente
            return redirect('inicio')  # ou o nome da sua página inicial
        else:
            return render(request, 'login.html', {'error': 'Usuário ou senha inválidos'})

    return render(request, 'login.html')

def inicio(request):
    return render(request, 'inicio.html')