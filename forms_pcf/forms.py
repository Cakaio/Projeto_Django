from django import forms
from .models import FeedbackArea, PedidoReembolso
from adm.models import Categoria


class FeedbackAreaForm(forms.ModelForm):
    class Meta:
        model = FeedbackArea
        fields = ['area', 'descricao']
        widgets = {
            'area': forms.Select(attrs={'class': 'form-select'}),
            'descricao': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 5,
                'placeholder': 'Descreva a dor ou problema da sua área...'
            }),
        }
        labels = {
            'area': 'Área',
            'descricao': 'Descrição',
        }


class PedidoReembolsoForm(forms.ModelForm):
    class Meta:
        model = PedidoReembolso
        fields = ['valor', 'descricao', 'data_gasto', 'categoria', 'comprovante']
        widgets = {
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'data_gasto': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'comprovante': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'valor': 'Valor (R$)',
            'descricao': 'Descrição do gasto',
            'data_gasto': 'Data do gasto',
            'categoria': 'Categoria',
            'comprovante': 'Comprovante (foto ou PDF)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = Categoria.objects.filter(tipo='DESPESA', ativo=True)
