from django import forms
from django.forms import inlineformset_factory
from .models import Semanario, Atividade, Material, COMPETENCIAS_SALAS

class SemanarioForm(forms.ModelForm):
    class Meta:
        model = Semanario
        fields = ["tema", "sala", "data", "projetor", "vagas", "talentos_necessarios"]

class AtividadeForm(forms.ModelForm):
    class Meta:
        model = Atividade
        fields = ["atividade", "descricao", "competencia", "tempo_atividade", "responsavel", "feedback", "local"]

    def __init__(self, *args, **kwargs):
        sala = kwargs.pop('sala', None)
        super().__init__(*args, **kwargs)
        # permitir que os forms extras do formset fiquem vazios sem gerar erro de validação
        self.fields['atividade'].required = False
        self.fields['descricao'].required = False
        self.fields['local'].required = False
        self.fields['feedback'].required = False

        if sala and sala in COMPETENCIAS_SALAS:
            self.fields['competencia'].widget = forms.Select(
                choices=[(c, c) for c in COMPETENCIAS_SALAS[sala]]
            )
        else:
            self.fields['competencia'].widget = forms.Select(choices=[('', '--- Escolha a sala primeiro ---')])


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ["nome", "quantidade", "unidade"]


# Cria os formsets
AtividadeFormSet = inlineformset_factory(
    Semanario,
    Atividade,
    form=AtividadeForm,
    extra=1,
    can_delete=True
)

MaterialFormSet = inlineformset_factory(
    Atividade,
    Material,
    form=MaterialForm,
    extra=1,
    can_delete=True
)