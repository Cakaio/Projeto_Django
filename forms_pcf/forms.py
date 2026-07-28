from django import forms
from .models import FeedbackArea, PedidoReembolso, ReceptorNotificacaoReembolso
from adm.models import Categoria


class FeedbackAreaForm(forms.ModelForm):
    class Meta:
        model = FeedbackArea
        fields = ['area', 'descricao', 'dor_geral', 'sugestao']
        widgets = {
            'area': forms.Select(attrs={'class': 'form-select'}),
            'descricao': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Ex.: falta de material, dificuldade com horários, comunicação...'
            }),
            'dor_geral': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Dores/desafios do PCF como um todo, além da sua área...'
            }),
            'sugestao': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Já teve uma ideia de solução ou projeto? Descreva aqui...'
            }),
        }
        labels = {
            'area': 'Sua área',
            'descricao': 'Dores da sua área',
            'dor_geral': 'Dores do PCF em geral',
            'sugestao': 'Sugestões de projetos',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ['descricao', 'dor_geral', 'sugestao']:
            self.fields[nome].required = False

    def clean(self):
        cleaned = super().clean()
        if not any(cleaned.get(n) for n in ['descricao', 'dor_geral', 'sugestao']):
            raise forms.ValidationError('Preencha ao menos uma das caixas (dor da área, dor geral ou sugestão).')
        return cleaned


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


class ReceptorNotificacaoReembolsoForm(forms.ModelForm):
    class Meta:
        model = ReceptorNotificacaoReembolso
        fields = ['nome', 'email', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome do receptor'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@exemplo.com'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'nome': 'Nome',
            'email': 'E-mail',
            'ativo': 'Ativo',
        }
