from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Sabado, DisponibilidadeVoluntario
from .forms import DisponibilidadeForm
# Create your views here.

@login_required
def responder_disponibilidade(request, sabado_id):
    sabado = get_object_or_404(Sabado, pk=sabado_id)

    if not sabado.enquete_aberta:
        messages.error(request, "⚠️ Esta enquete já foi encerrada.")
        return redirect("inicio")

    # pega ou cria a resposta do voluntário (1 por sábado)
    obj, created = DisponibilidadeVoluntario.objects.get_or_create(
        sabado=sabado,
        voluntario=request.user,
        defaults={"vai_ao_projeto": False}
    )

    if request.method == "POST":
        form = DisponibilidadeForm(request.POST, instance=obj)

        if form.is_valid():
            resposta = form.save(commit=False)

            # garante no backend (anti-gambiarra no front)
            resposta.sabado = sabado
            resposta.voluntario = request.user

            resposta.save()
            form.save_m2m()  # salva o ManyToMany (pode_ajudar)

            messages.success(request, "✅ Resposta atualizada com sucesso!")
            return redirect("sabado:responder_disponibilidade", sabado_id=sabado.id)

        else:
            messages.error(request, "❌ Há erros no formulário. Confira os campos.")
    else:
        form = DisponibilidadeForm(instance=obj)

    return render(request, "responder_disponibilidade.html", {
        "sabado": sabado,
        "form": form,
        "created": created,  # opcional (debug)
    })