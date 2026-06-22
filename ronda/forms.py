# ronda/forms.py
from django import forms
from django.forms import inlineformset_factory
from .models import LocalRonda, ConfiguracaoRondaSabado, HorarioRonda, ScoreRonda


class LocalRondaForm(forms.ModelForm):
    class Meta:
        model = LocalRonda
        fields = ['nome', 'ativo', 'ordem']
        widgets = {
            'nome':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Quadra'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'ordem': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
        labels = {'nome': 'Nome', 'ativo': 'Ativo', 'ordem': 'Ordem de exibição'}


class ConfiguracaoRondaForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoRondaSabado
        fields = ['sabado']
        widgets = {'sabado': forms.Select(attrs={'class': 'form-select'})}
        labels = {'sabado': 'Sábado'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from sabado.models import Sabado
        from django.utils import timezone
        ja_configurados = ConfiguracaoRondaSabado.objects.values_list('sabado_id', flat=True)
        self.fields['sabado'].queryset = (
            Sabado.objects.filter(data__gte=timezone.now().date())
            .exclude(pk__in=ja_configurados)
            .order_by('data')
        )


class HorarioRondaForm(forms.ModelForm):
    class Meta:
        model = HorarioRonda
        fields = ['hora_inicio', 'hora_fim', 'ordem']
        widgets = {
            'hora_inicio': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'hora_fim':    forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'ordem':       forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
        labels = {'hora_inicio': 'Início', 'hora_fim': 'Fim', 'ordem': 'Ordem'}


HorarioRondaFormSet = inlineformset_factory(
    ConfiguracaoRondaSabado,
    HorarioRonda,
    form=HorarioRondaForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class ScoreRondaForm(forms.ModelForm):
    class Meta:
        model = ScoreRonda
        fields = ['pontos']
        widgets = {'pontos': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'})}
        labels = {'pontos': 'Pontos (rondas feitas no ano)'}
