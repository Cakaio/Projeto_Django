from django import forms
from django.forms import modelformset_factory

from .models import Revista, SecaoRevista


class RevistaForm(forms.ModelForm):
    class Meta:
        model = Revista
        fields = ['titulo', 'subtitulo', 'periodo_inicio', 'periodo_fim',
                  'texto_abertura', 'texto_fechamento', 'mostrar_numeros',
                  'mostrar_financeiro', 'link_publico_ativo', 'link_expira_em']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'pcf-input'}),
            'subtitulo': forms.TextInput(attrs={'class': 'pcf-input'}),
            'periodo_inicio': forms.DateInput(attrs={'class': 'pcf-input', 'type': 'date'},
                                              format='%Y-%m-%d'),
            'periodo_fim': forms.DateInput(attrs={'class': 'pcf-input', 'type': 'date'},
                                           format='%Y-%m-%d'),
            'link_expira_em': forms.DateInput(attrs={'class': 'pcf-input', 'type': 'date'},
                                              format='%Y-%m-%d'),
            'texto_abertura': forms.Textarea(attrs={'class': 'pcf-input', 'rows': 5}),
            'texto_fechamento': forms.Textarea(attrs={'class': 'pcf-input', 'rows': 4}),
        }
        help_texts = {
            'link_expira_em': 'Opcional. Depois desta data o link do doador para de abrir.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # `type="date"` só preenche o valor se ele vier no formato ISO.
        for campo in ('periodo_inicio', 'periodo_fim', 'link_expira_em'):
            self.fields[campo].input_formats = ['%Y-%m-%d']
        self.fields['titulo'].widget.attrs['placeholder'] = 'Ex.: Criança Feliz — 1º semestre'
        self.fields['subtitulo'].widget.attrs['placeholder'] = 'Uma linha que resume o período'

    def clean(self):
        dados = super().clean()
        inicio = dados.get('periodo_inicio')
        fim = dados.get('periodo_fim')
        if inicio and fim and fim < inicio:
            self.add_error('periodo_fim', 'O fim do período não pode ser antes do início.')
        return dados


SecaoRevistaFormSet = modelformset_factory(
    SecaoRevista,
    fields=('incluir', 'titulo', 'texto', 'competencia', 'ordem', 'foto_propria'),
    extra=0,
    can_delete=True,
    widgets={
        'titulo': forms.TextInput(attrs={'class': 'pcf-input'}),
        'texto': forms.Textarea(attrs={'class': 'pcf-input', 'rows': 4}),
        'competencia': forms.TextInput(attrs={'class': 'pcf-input'}),
        'ordem': forms.NumberInput(attrs={'class': 'pcf-input', 'min': 0}),
    },
)
