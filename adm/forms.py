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
    """Um teto por área, que vale até alguém alterar ou excluir.

    Não há campo de mês: o teto não é cadastrado por período. `vigente_desde` é
    memória de quando o valor passou a valer, não recorte do gasto.
    """

    class Meta:
        model = TetoArea
        fields = ['area', 'valor', 'vigente_desde', 'observacao']
        widgets = {
            'valor': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'vigente_desde': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'observacao': forms.TextInput(
                attrs={'placeholder': 'Ex.: combinado na reunião de fevereiro'}),
        }
        labels = {
            'area': 'Área',
            'valor': 'Teto por semestre (R$)',
            'vigente_desde': 'Vale a partir de',
            'observacao': 'Observação',
        }
        help_texts = {
            'valor': 'Quanto a área pode gastar no semestre. Vale até alguém alterar ou excluir.',
            'vigente_desde': 'Só para registro de quando foi combinado.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['vigente_desde'].input_formats = ['%Y-%m-%d']
        if not self.instance.pk:
            self.fields['vigente_desde'].initial = timezone.localdate()
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')

    def clean_area(self):
        """Uma área não pode ter dois tetos.

        O `unique=True` do model já barraria, mas com a mensagem crua do banco,
        que não diz o que fazer. Aqui o recado aponta para a saída: editar o
        que já existe.
        """
        area = self.cleaned_data['area']
        existente = TetoArea.objects.filter(area=area)
        if self.instance.pk:
            existente = existente.exclude(pk=self.instance.pk)
        if existente.exists():
            rotulo = dict(self.fields['area'].choices).get(area, area)
            raise forms.ValidationError(
                f'{rotulo} já tem teto definido. Edite o que está lá em vez de criar outro.')
        return area


class CompletarLancamentoForm(forms.ModelForm):
    """Só conta e área, para lançamento gerado por outro app.

    Valor, data, categoria e origem continuam trancados: a fonte da verdade é o
    registro que criou o lançamento (pedido do Supply, reembolso, doação), e
    editar dos dois lados deixaria os dois divergentes.

    Mas quem sabe de qual cartão saiu o dinheiro é o ADM, na hora de pagar —
    não o voluntário que pediu o material. Sem esta tela, o gasto do Supply
    ficava para sempre sem banco, contrariando o pedido de que TODA entrada e
    saída diga de onde saiu.
    """

    class Meta:
        model = Lancamento
        fields = ['conta', 'area']
        labels = {'conta': 'De onde saiu (ou entrou)', 'area': 'Área'}
        help_texts = {
            'conta': 'Banco, cartão ou dinheiro físico.',
            'area': 'Deixe como está se a origem já preencheu certo.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['conta'].queryset = Conta.objects.filter(ativo=True)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')
