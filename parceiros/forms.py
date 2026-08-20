from django import forms
from django.utils import timezone

from adm.models import Conta
from voluntario.models import Voluntario

from .models import Contribuicao, Interacao, Parceiro

# Quem pode ser responsável por uma carteira.
AREAS_CARTEIRA = ('CR/RE', 'TRIADE')


def _voluntarios_carteira():
    """Voluntários ativos que podem assumir uma carteira (CR/RE e Tríade)."""
    return (Voluntario.objects
            .filter(data_saida__isnull=True, area__in=AREAS_CARTEIRA)
            .order_by('first_name', 'username'))


class ParceiroForm(forms.ModelForm):
    class Meta:
        model = Parceiro
        fields = ['nome', 'responsavel', 'status', 'email', 'telefone',
                  'documento', 'valor_referencia', 'observacoes']
        widgets = {
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsavel'].queryset = _voluntarios_carteira()
        self.fields['responsavel'].empty_label = 'Sem responsável'
        for nome, campo in self.fields.items():
            campo.widget.attrs.setdefault('class', 'pcf-input')
        self.fields['nome'].widget.attrs['placeholder'] = 'Nome completo, como sai no recibo'
        self.fields['telefone'].widget.attrs['placeholder'] = '(00) 00000-0000'


class ContribuicaoForm(forms.ModelForm):
    # O usuário escolhe o mês; o dia é normalizado no model.
    competencia = forms.DateField(
        label='Mês de referência',
        widget=forms.DateInput(attrs={'type': 'month', 'class': 'pcf-input'}),
        input_formats=['%Y-%m', '%Y-%m-%d'],
    )

    class Meta:
        model = Contribuicao
        fields = ['parceiro', 'competencia', 'valor', 'data_recebimento', 'forma',
                  'conta', 'observacao']
        widgets = {
            'data_recebimento': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parceiro'].queryset = Parceiro.objects.exclude(status='ENCERRADO')
        # Conta desativada continua no histórico, mas não deve ser oferecida
        # para uma doação nova.
        self.fields['conta'].queryset = Conta.objects.filter(ativo=True)
        self.fields['conta'].empty_label = 'Não informado'
        self.fields['data_recebimento'].input_formats = ['%Y-%m-%d']
        self.fields['data_recebimento'].initial = timezone.localdate()
        self.fields['data_recebimento'].help_text = (
            'Data em que o dinheiro entrou — é ela que vale no fluxo de caixa e no DRE.'
        )
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')
        if self.instance and self.instance.pk and self.instance.competencia:
            self.initial['competencia'] = self.instance.competencia.strftime('%Y-%m')

    def clean_competencia(self):
        data = self.cleaned_data['competencia']
        return data.replace(day=1) if data else data

    def clean(self):
        limpos = super().clean()
        parceiro, competencia = limpos.get('parceiro'), limpos.get('competencia')
        if parceiro and competencia:
            existente = Contribuicao.objects.filter(parceiro=parceiro, competencia=competencia)
            if self.instance.pk:
                existente = existente.exclude(pk=self.instance.pk)
            if existente.exists():
                self.add_error(
                    'competencia',
                    f'Já existe contribuição de {parceiro} em {competencia:%m/%Y}. '
                    'Edite a que já está lançada em vez de criar outra.',
                )
        return limpos


class InteracaoForm(forms.ModelForm):
    class Meta:
        model = Interacao
        fields = ['data', 'tipo', 'descricao']
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'descricao': forms.Textarea(attrs={'rows': 3, 'placeholder': 'O que foi conversado?'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data'].input_formats = ['%Y-%m-%d']
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')
