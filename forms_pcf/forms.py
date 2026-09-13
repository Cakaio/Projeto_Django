from django import forms
from django.utils import timezone
from .models import FeedbackArea, PedidoReembolso, ReceptorNotificacaoReembolso
from adm.models import Categoria, Conta, Evento


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
    """O pedido de reembolso, incluindo de QUEM é o gasto.

    A área já saiu automaticamente da área do solicitante, e isso mentia: quem
    é do Amarelo e abastece o carro para buscar material não gastou dinheiro do
    Amarelo. O teto da salinha encolhia por causa de gasolina, e a única
    correção estava na tela de pagamento — se a ADM esquecesse, ficava errado
    para sempre.

    Três saídas, porque são as três que o modelo já sabia representar: área
    (desconta o teto dela), evento (não desconta área nenhuma) e nada dos dois
    (não desconta teto nenhum).
    """

    DESTINO_AREA = 'AREA'
    DESTINO_EVENTO = 'EVENTO'
    DESTINO_GERAL = 'GERAL'

    # Sem isto, `destino` e `evento` cairiam no FIM do formulário: o ModelForm
    # monta os campos do Meta primeiro e só depois acrescenta os declarados na
    # classe. A pergunta "de quem é o gasto" tem que vir junto da categoria.
    field_order = ['valor', 'descricao', 'data_gasto', 'categoria',
                   'destino', 'evento', 'comprovante']

    destino = forms.ChoiceField(
        label='De quem é este gasto?',
        initial=DESTINO_AREA,
        widget=forms.RadioSelect,
        choices=(
            (DESTINO_AREA, 'Da minha área'),
            (DESTINO_EVENTO, 'De um evento'),
            (DESTINO_GERAL, 'Do projeto em geral'),
        ),
    )

    class Meta:
        model = PedidoReembolso
        fields = ['valor', 'descricao', 'data_gasto', 'categoria', 'comprovante', 'evento']
        widgets = {
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'data_gasto': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'comprovante': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'evento': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'valor': 'Valor (R$)',
            'descricao': 'Descrição do gasto',
            'data_gasto': 'Data do gasto',
            'categoria': 'Categoria',
            'comprovante': 'Comprovante (foto ou PDF) — opcional',
            'evento': 'Qual evento',
        }

    def __init__(self, *args, voluntario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.voluntario = voluntario
        self.fields['categoria'].queryset = Categoria.objects.filter(tipo='DESPESA', ativo=True)
        self.fields['evento'].queryset = Evento.objects.filter(ativo=True)
        self.fields['evento'].required = False
        self.fields['evento'].empty_label = 'Escolha o evento'

        # "Da minha área" precisa DIZER qual área é, senão a pessoa marca sem
        # saber o que está afirmando — e a área é justamente o que está em jogo.
        area = getattr(voluntario, 'area', '') or ''
        if area:
            rotulo = voluntario.get_area_display()
            self.fields['destino'].choices = [
                (self.DESTINO_AREA, f'Da minha área — {rotulo}'),
                (self.DESTINO_EVENTO, 'De um evento'),
                (self.DESTINO_GERAL, 'Do projeto em geral'),
            ]
        # Sem comprovante o pedido entra do mesmo jeito: quem decide se vale é a
        # ADM/Fin, na aprovação. Antes o formulário barrava, e gasto sem nota
        # (estacionamento, feira, troco de ônibus) simplesmente não era pedido.
        self.fields['comprovante'].required = False
        self.fields['comprovante'].help_text = (
            'Se tiver, anexe — acelera a aprovação. Se não tiver, mande assim '
            'mesmo e explique na descrição.'
        )

    def clean(self):
        dados = super().clean()
        destino = dados.get('destino')

        if destino == self.DESTINO_EVENTO and not dados.get('evento'):
            self.add_error('evento', 'Escolha o evento a que este gasto pertence.')
        elif destino != self.DESTINO_EVENTO:
            # O rádio muda, o select fica preenchido. Sem limpar, o pedido sairia
            # marcado com um evento que a pessoa não quis — e o gasto apareceria
            # no relatório do evento errado.
            dados['evento'] = None

        return dados

    def area_escolhida(self):
        """A área que o pedido deve carregar, já traduzida da escolha.

        Evento e "projeto em geral" devolvem vazio, e vazio não conta em teto
        nenhum (`adm.servicos._despesa_agrupada_por_area` ignora). É de
        propósito: gasolina da Festa Junina não é gasto do Amarelo, e também
        não é da equipe de Eventos, que é um time e não o evento.
        """
        if self.cleaned_data.get('destino') != self.DESTINO_AREA:
            return ''
        return getattr(self.voluntario, 'area', '') or ''


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


class PagamentoReembolsoForm(forms.ModelForm):
    """O que o ADM preenche quando o reembolso é de fato pago.

    Área e evento entram aqui porque é o ADM quem sabe a qual teto o gasto
    pertence — e sem eles o reembolso pago não apareceria no teto da área, que
    é metade do que o pedido pediu.
    """

    class Meta:
        model = PedidoReembolso
        fields = ['conta_pagamento', 'comprovante_pagamento', 'pago_em', 'area', 'evento']
        widgets = {
            'pago_em': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }
        labels = {
            'conta_pagamento': 'De onde saiu o pagamento',
            'comprovante_pagamento': 'Comprovante do pagamento',
            'pago_em': 'Data do pagamento',
            'area': 'Área que gastou',
            'evento': 'Evento (se for de um evento)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Os dois são opcionais no model (histórico antigo não tem), mas
        # obrigatórios para marcar como PAGO: dinheiro que saiu sem comprovante
        # e sem conta não tem como ser conferido depois.
        self.fields['conta_pagamento'].required = True
        self.fields['comprovante_pagamento'].required = True
        self.fields['conta_pagamento'].queryset = Conta.objects.filter(ativo=True)
        self.fields['conta_pagamento'].empty_label = 'Escolha a conta'
        self.fields['evento'].queryset = Evento.objects.filter(ativo=True)
        self.fields['evento'].empty_label = 'Nenhum'
        self.fields['pago_em'].input_formats = ['%Y-%m-%d']
        self.fields['pago_em'].required = False
        if not self.instance.pago_em:
            self.fields['pago_em'].initial = timezone.localdate()
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')
