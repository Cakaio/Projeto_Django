from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from django.db import models


from sabado.models import Sabado

class inicio(TemplateView):
    template_name = "inicio.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sabados_abertos'] = Sabado.objects.filter(data__gte=models.functions.Now()).order_by('data')
        context['sabados_abertos'] = [s for s in context['sabados_abertos'] if s.enquete_aberta]
        return context
