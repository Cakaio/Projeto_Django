# semanario/forms.py
from django import forms
from django.forms import modelformset_factory
from .models import Semanario

class SemanarioForm(forms.ModelForm):
    class Meta:
        model = Semanario
        fields = ["sala", "data", "atividade", "descricao", "competencia", "tempo_atividade", "responsavel"]

# Cria um FormSet baseado nesse formulário
SemanarioFormSet = modelformset_factory(Semanario, form=SemanarioForm, extra=1)

