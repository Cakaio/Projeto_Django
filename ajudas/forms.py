from django import forms

from voluntario.models import LISTA_AREAS


class RevisaoForm(forms.Form):
    revisao = forms.IntegerField(min_value=0)


class EscalaForm(RevisaoForm):
    hora_inicio = forms.TimeField(input_formats=["%H:%M"])
    hora_fim = forms.TimeField(input_formats=["%H:%M"])


class NecessidadeForm(forms.Form):
    area = forms.ChoiceField(choices=LISTA_AREAS)
    hora_inicio = forms.TimeField(input_formats=["%H:%M"])
    hora_fim = forms.TimeField(input_formats=["%H:%M"])
    quantidade = forms.IntegerField(min_value=0, max_value=100000)


class AjudaForm(forms.Form):
    voluntario = forms.IntegerField(min_value=1)
    area_destino = forms.ChoiceField(choices=LISTA_AREAS)
    hora_inicio = forms.TimeField(input_formats=["%H:%M"])
    hora_fim = forms.TimeField(input_formats=["%H:%M"])
