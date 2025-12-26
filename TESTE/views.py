from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect

def homepage_inicial(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("/atendido/")  # Redirect to a named URL pattern after login
        else:
            return render(request, 'homepage_inicial.html', {"error": "Usuário ou senha inválidos."})
    return render(request, 'homepage_inicial.html')
