from django import forms
from .models import Categoria, Lancamento


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nome', 'tipo', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Doação'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nome': 'Nome da Categoria',
            'tipo': 'Tipo',
            'ativo': 'Ativa',
        }


class LancamentoForm(forms.ModelForm):
    class Meta:
        model = Lancamento
        fields = ['categoria', 'valor', 'data', 'descricao', 'origem']
