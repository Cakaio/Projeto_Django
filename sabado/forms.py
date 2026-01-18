from django import forms
from .models import DisponibilidadeVoluntario, FaixaHorarioAjuda

class DisponibilidadeForm(forms.ModelForm):
    pode_ajudar = forms.ModelMultipleChoiceField(
        queryset=FaixaHorarioAjuda.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    # Removido: vai_ao_projeto será tratado pelo ModelForm

    class Meta:
        model = DisponibilidadeVoluntario
        fields = ["vai_ao_projeto", "pode_ajudar", "vai_de_carro", "saude"]
        widgets = {
            "saude": forms.RadioSelect(choices=[(True, "Estou bem 100%"), (False, "Não me senti bem essa semana")]),
            "vai_ao_projeto": forms.RadioSelect(choices=[(True, "Vou"), (False, "Não vou")]),
            "vai_de_carro": forms.RadioSelect(choices=[(True, "Sim"), (False, "Não")]),
        }