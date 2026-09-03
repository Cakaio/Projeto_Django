from django import forms

from voluntario.models import Voluntario

from .coleta import chave_do_link
from .models import ConsultaBusca, Edital, FonteEdital, PalavraChave

# Quem pode ficar responsável por concorrer a um edital.
AREAS_RESPONSAVEL = ('CR/RE', 'TRIADE')


def _aplicar_estilo(form):
    """Todo campo entra com a classe do design system, sem repetir widget."""
    for campo in form.fields.values():
        if isinstance(campo.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
            continue
        campo.widget.attrs.setdefault('class', 'pcf-input')


class EditalForm(forms.ModelForm):
    class Meta:
        model = Edital
        fields = ['titulo', 'link', 'descricao', 'requisitos', 'prazo', 'valor',
                  'status', 'responsavel', 'fonte', 'observacoes']
        widgets = {
            'prazo': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'descricao': forms.Textarea(attrs={'rows': 4}),
            'requisitos': forms.Textarea(
                attrs={'rows': 3,
                       'placeholder': 'Certidões, tempo de CNPJ, contrapartida, prestação de contas...'}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['prazo'].input_formats = ['%Y-%m-%d']
        self.fields['responsavel'].queryset = (
            Voluntario.objects.ativos()
            .filter(area__in=AREAS_RESPONSAVEL)
            .order_by('first_name', 'username'))
        self.fields['responsavel'].empty_label = 'Sem responsável'
        self.fields['fonte'].empty_label = 'Cadastro manual'
        self.fields['fonte'].required = False
        _aplicar_estilo(self)

    def clean_link(self):
        """O link é a identidade do edital: dois cadastros do mesmo link
        viram duas conversas paralelas sobre a mesma chamada."""
        link = self.cleaned_data['link']
        repetidos = Edital.objects.filter(chave=chave_do_link(link))
        if self.instance.pk:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise forms.ValidationError('Esse link já está cadastrado. Abra o edital que já existe.')
        return link

    def save(self, commit=True):
        # Se o link mudou, a chave de dedupe precisa mudar junto — senão o robô
        # continuaria comparando pela chave antiga e recadastraria o edital.
        self.instance.chave = chave_do_link(self.instance.link)
        return super().save(commit)


class FonteEditalForm(forms.ModelForm):
    class Meta:
        model = FonteEdital
        fields = ['nome', 'url', 'tipo', 'ativo', 'seletor_item', 'seletor_titulo',
                  'seletor_link', 'seletor_descricao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['seletor_item'].widget.attrs['placeholder'] = 'ex.: article.edital'
        self.fields['seletor_titulo'].widget.attrs['placeholder'] = 'ex.: h2 a'
        self.fields['seletor_link'].widget.attrs['placeholder'] = 'ex.: h2 a'
        self.fields['seletor_descricao'].widget.attrs['placeholder'] = 'ex.: p.resumo'
        _aplicar_estilo(self)

    def clean(self):
        limpos = super().clean()
        # Sem o seletor do item, a leitura de HTML não sabe onde cada edital
        # começa e acabaria trazendo a página inteira como um item só.
        if limpos.get('tipo') == 'HTML' and not (limpos.get('seletor_item') or '').strip():
            self.add_error('seletor_item', 'Fonte HTML precisa do seletor de cada item da lista.')
        return limpos


class ConsultaBuscaForm(forms.ModelForm):
    class Meta:
        model = ConsultaBusca
        fields = ['termo', 'ativo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['termo'].widget.attrs['placeholder'] = (
            'ex.: edital FIA CMDCA 2026 fundo da infância e adolescência')
        self.fields['termo'].help_text = (
            'Escreva como você escreveria numa busca. Termo concreto '
            '(FIA, CMDCA, contraturno) traz mais edital de verdade do que '
            'palavra genérica.')
        _aplicar_estilo(self)

    def clean_termo(self):
        return (self.cleaned_data['termo'] or '').strip()


class PalavraChaveForm(forms.ModelForm):
    class Meta:
        model = PalavraChave
        fields = ['termo', 'peso', 'ativo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['termo'].widget.attrs['placeholder'] = 'ex.: primeira infância'
        self.fields['peso'].help_text = (
            'De 1 a 3 para o que interessa; de -1 a -3 para o que deve ser descartado.')
        _aplicar_estilo(self)

    def clean_termo(self):
        return (self.cleaned_data['termo'] or '').strip()
