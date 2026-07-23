from django import forms
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory

from .models import Atendido, Familia, ResponsavelAtendido, AtendidoInclusivo


def _compactar_textareas(form):
    """Deixa os textareas com altura razoável (default do Django é grande demais)."""
    for f in form.fields.values():
        if isinstance(f.widget, forms.Textarea):
            f.widget.attrs.setdefault('rows', 3)


class AtendidoForm(forms.ModelForm):
    class Meta:
        model = Atendido
        # familia/responsavel/registrado_por/data_criacao/ativo são tratados pela view
        exclude = ['familia', 'responsavel', 'registrado_por', 'data_criacao', 'ativo']
        widgets = {
            'data_nascimento': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'aspectos_mudancas': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['matricula'].required = True
        self.fields['data_nascimento'].input_formats = ['%Y-%m-%d']
        _compactar_textareas(self)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('cpf') and not cleaned.get('rg'):
            self.add_error('cpf', 'Informe ao menos o CPF ou o RG da criança.')
        return cleaned


class FamiliaForm(forms.ModelForm):
    class Meta:
        model = Familia
        exclude = ['data_criacao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ['cep', 'bairro', 'cidade']:
            self.fields[nome].required = True
        _compactar_textareas(self)


class ResponsavelAtendidoForm(forms.ModelForm):
    class Meta:
        model = ResponsavelAtendido
        exclude = ['data_criacao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ['nome', 'parentesco', 'contato']:
            self.fields[nome].required = True

    def validate_unique(self):
        # Reaproveitamento por CPF é tratado na view — não bloquear aqui.
        exclude = self._get_validation_exclusions()
        exclude.add('cpf')
        try:
            self.instance.validate_unique(exclude=exclude)
        except ValidationError as e:
            self._update_errors(e)


class AtendidoInclusivoForm(forms.ModelForm):
    class Meta:
        model = AtendidoInclusivo
        exclude = ['atendido']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Booleanos anuláveis do modelo -> checkbox simples (renderizados como Sim/Não)
        for nome in ['diagnostico', 'acompanhamento', 'servicos_apoio']:
            antigo = self.fields[nome]
            self.fields[nome] = forms.BooleanField(
                required=False,
                label=antigo.label,
                help_text=antigo.help_text,
                initial=bool(getattr(self.instance, nome, False)),
            )
        _compactar_textareas(self)


ResponsavelFormSet = modelformset_factory(
    ResponsavelAtendido,
    form=ResponsavelAtendidoForm,
    extra=1,
    min_num=1,
    validate_min=True,
    can_delete=True,
)
