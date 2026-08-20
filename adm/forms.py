from django import forms
from django.utils import timezone

from voluntario.models import Voluntario

from .models import Categoria, Conta, Evento, Lancamento, RecargaCartao, TetoArea


def _voluntarios_ativos():
    """Quem está no projeto hoje. Desligado não pode virar responsável de
    cartão novo, mas continua no histórico do que já assinou."""
    return Voluntario.objects.ativos().order_by('first_name', 'username')


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
        fields = ['categoria', 'valor', 'data', 'conta', 'area', 'evento', 'descricao']
        widgets = {
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'data': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'conta': forms.Select(attrs={'class': 'form-select'}),
            'area': forms.Select(attrs={'class': 'form-select'}),
            'evento': forms.Select(attrs={'class': 'form-select'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'categoria': 'Categoria',
            'valor': 'Valor (R$)',
            'data': 'Data do Fato',
            'conta': 'Banco / cartão / dinheiro',
            'area': 'Área',
            'evento': 'Evento',
            'descricao': 'Descrição (opcional)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = Categoria.objects.filter(ativo=True)
        # Conta e evento desativados seguem no histórico, mas oferecê-los num
        # lançamento novo só produziria dado que ninguém quer mais usar.
        self.fields['conta'].queryset = Conta.objects.filter(ativo=True)
        self.fields['conta'].empty_label = 'Não informado'
        self.fields['evento'].queryset = Evento.objects.filter(ativo=True)
        self.fields['evento'].empty_label = 'Nenhum'


class ContaForm(forms.ModelForm):
    class Meta:
        model = Conta
        fields = ['nome', 'tipo', 'controla_saldo', 'responsavel', 'ativo', 'observacao']
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Ex.: Caju — cartão da Recreação'}),
            'observacao': forms.TextInput(attrs={'placeholder': 'Ex.: cartão físico, fica na sede'}),
        }
        labels = {
            'nome': 'Nome da conta',
            'tipo': 'Tipo',
            'responsavel': 'Com quem está',
            'ativo': 'Ativa',
            'observacao': 'Observação',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['responsavel'].queryset = _voluntarios_ativos()
        self.fields['responsavel'].empty_label = 'Ninguém / não se aplica'
        for nome, campo in self.fields.items():
            if nome not in ('controla_saldo', 'ativo'):
                campo.widget.attrs.setdefault('class', 'pcf-input')


class RecargaCartaoForm(forms.ModelForm):
    class Meta:
        model = RecargaCartao
        fields = ['conta', 'data', 'valor', 'area', 'carregado_por', 'motivo']
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'valor': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'motivo': forms.TextInput(attrs={'placeholder': 'Ex.: compras do sábado 12/04'}),
        }
        labels = {
            'conta': 'Cartão / conta recarregada',
            'data': 'Data da recarga',
            'valor': 'Valor (R$)',
            'carregado_por': 'Quem carregou',
            'motivo': 'Motivo',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data'].input_formats = ['%Y-%m-%d']
        if not self.instance.pk:
            self.fields['data'].initial = timezone.localdate()
        self.fields['conta'].queryset = Conta.objects.filter(ativo=True)
        self.fields['conta'].empty_label = 'Escolha o cartão'
        self.fields['conta'].help_text = (
            'O saldo só aparece no painel se a conta estiver marcada como '
            '"controlar saldo".'
        )
        self.fields['carregado_por'].queryset = _voluntarios_ativos()
        self.fields['carregado_por'].empty_label = 'Não informado'
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')


class TetoAreaForm(forms.ModelForm):
    # O usuário escolhe o mês; o dia é normalizado no model.
    competencia = forms.DateField(
        label='Mês de referência',
        widget=forms.DateInput(attrs={'type': 'month', 'class': 'pcf-input'}),
        input_formats=['%Y-%m', '%Y-%m-%d'],
        help_text='O teto é mensal: zera todo dia 1º.',
    )

    class Meta:
        model = TetoArea
        fields = ['area', 'competencia', 'valor', 'observacao']
        widgets = {
            'valor': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'observacao': forms.TextInput(attrs={'placeholder': 'Ex.: mês de festa junina'}),
        }
        labels = {
            'area': 'Área',
            'valor': 'Teto do mês (R$)',
            'observacao': 'Observação',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['competencia'].initial = timezone.localdate().strftime('%Y-%m')
        elif self.instance.competencia:
            self.initial['competencia'] = self.instance.competencia.strftime('%Y-%m')
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')

    def clean_competencia(self):
        data = self.cleaned_data['competencia']
        return data.replace(day=1) if data else data

    def clean(self):
        limpos = super().clean()
        area, competencia = limpos.get('area'), limpos.get('competencia')
        if area and competencia:
            existente = TetoArea.objects.filter(area=area, competencia=competencia)
            if self.instance.pk:
                existente = existente.exclude(pk=self.instance.pk)
            if existente.exists():
                # A UniqueConstraint já barraria, mas com a mensagem crua do
                # banco ("constraint ... is violated"), que não diz o que fazer.
                self.add_error(
                    'competencia',
                    f'Já existe teto de {dict(self.fields["area"].choices).get(area, area)} '
                    f'em {competencia:%m/%Y}. Edite o que já está lá em vez de criar outro.',
                )
        return limpos
