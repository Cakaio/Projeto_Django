# ronda/forms.py
from django import forms
from django.forms import inlineformset_factory
from .models import LocalRonda, ConfiguracaoRondaSabado, HorarioRonda, ScoreRonda


class LocalRondaForm(forms.ModelForm):
    class Meta:
        model = LocalRonda
        fields = ['nome', 'ativo']
        widgets = {
            'nome':  forms.TextInput(attrs={'placeholder': 'Ex: Quadra'}),
            'ativo': forms.CheckboxInput(),
        }
        labels = {'nome': 'Nome do local', 'ativo': 'Local ativo'}


class ConfiguracaoRondaForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoRondaSabado
        fields = ['sabado', 'dia_de_evento']
        widgets = {
            'sabado': forms.Select(attrs={'class': 'form-select'}),
            'dia_de_evento': forms.CheckboxInput(),
        }
        labels = {'sabado': 'Sábado', 'dia_de_evento': 'Ronda em dia de evento'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from sabado.models import Sabado
        from django.utils import timezone
        from datetime import timedelta
        ja_configurados = ConfiguracaoRondaSabado.objects.values_list('sabado_id', flat=True)
        limite = timezone.now().date() - timedelta(days=30)
        self.fields['sabado'].queryset = (
            Sabado.objects.filter(data__gte=limite)
            .exclude(pk__in=ja_configurados)
            .order_by('data')
        )


class HorarioRondaForm(forms.ModelForm):
    class Meta:
        model = HorarioRonda
        fields = ['hora_inicio', 'hora_fim', 'local']
        widgets = {
            'hora_inicio': forms.TimeInput(attrs={'type': 'time'}),
            'hora_fim':    forms.TimeInput(attrs={'type': 'time'}),
            'local':       forms.Select(),
        }
        labels = {'hora_inicio': 'Início', 'hora_fim': 'Fim', 'local': 'Local'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['local'].queryset = LocalRonda.objects.filter(ativo=True)
        self.fields['local'].required = True
        self.fields['local'].empty_label = 'Selecione o local…'
        # Horários são opcionais: no modo "dia de evento" não há faixa de horário.
        self.fields['hora_inicio'].required = False
        self.fields['hora_fim'].required = False


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
