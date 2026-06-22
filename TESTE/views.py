from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from django.db import models
from voluntario.models import Voluntario
from django.utils import timezone
from django.db.models import Count, Value, IntegerField, F

from sabado.models import Sabado
from ronda.models import ConfiguracaoRondaSabado


class inicio(TemplateView):
    template_name = "inicio.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Voluntários ATIVOS = sem data_saida
        total_ativos = Voluntario.objects.filter(data_saida__isnull=True).count()

        sabados_qs = (
            Sabado.objects
            .filter(data__gte=timezone.now().date())
            .order_by("data")
            .annotate(respostas_count=Count("disponibilidades", distinct=True))
        )

        sabados_abertos = []
        for s in sabados_qs:
            if not s.enquete_aberta:
                continue

            s.total_voluntarios_ativos = total_ativos
            s.total_respostas_view = s.respostas_count
            s.total_nao_responderam = max(0, total_ativos - s.total_respostas_view)

            if total_ativos == 0:
                s.percentual_respostas_int = 0
            else:
                pct = (s.total_respostas_view / total_ativos) * 100
                s.percentual_respostas_int = int(round(max(0, min(100, pct))))

            sabados_abertos.append(s)

        context["sabados_abertos"] = sabados_abertos

        context["proxima_ronda"] = (
            ConfiguracaoRondaSabado.objects
            .filter(status='APROVADA', sabado__data__gte=timezone.now().date())
            .select_related('sabado')
            .order_by('sabado__data')
            .first()
        )

        return context