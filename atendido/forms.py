from django import forms
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory

from .models import Atendido, Familia, ResponsavelAtendido, AtendidoInclusivo, ListaEspera


def _compactar_textareas(form):
    for f in form.fields.values():
        if isinstance(f.widget, forms.Textarea):
            f.widget.attrs.setdefault('rows', 3)


def _mascarar(form, campos):
    """Aplica máscara visual (formatada no cliente; dígitos são enviados no submit).
    campos = {nome: (tipo, placeholder, maxlength_visual)}"""
    for nome, (tipo, placeholder, maxlen) in campos.items():
        f = form.fields.get(nome)
        if f:
            f.widget.attrs.update({
                'data-mask': tipo,
                'inputmode': 'numeric',
                'placeholder': placeholder,
                'maxlength': maxlen,
            })


def _para_coerce(v):
    return v == 'True'


def _boolean_para_simnao(form):
    """Converte BooleanField/NullBooleanField em Sim/Não (radio nativo, robusto)."""
    for nome, field in list(form.fields.items()):
        if isinstance(field, (forms.BooleanField, forms.NullBooleanField)) and not isinstance(field, forms.TypedChoiceField):
            atual = getattr(form.instance, nome, None) if getattr(form, 'instance', None) else None
            valor = 'True' if atual else 'False'
            form.fields[nome] = forms.TypedChoiceField(
                choices=[('True', 'Sim'), ('False', 'Não')],
                coerce=_para_coerce,
                empty_value=False,
                required=False,
                widget=forms.RadioSelect,
                label=field.label,
                help_text=field.help_text,
                initial=valor,
            )
            # Sobrepõe o initial do ModelForm (bool vindo da instância) por string,
            # para o template comparar field.value com 'True'/'False'.
            form.initial[nome] = valor


class AtendidoForm(forms.ModelForm):
    class Meta:
        model = Atendido
        exclude = ['familia', 'responsavel', 'registrado_por', 'data_criacao', 'ativo']
        widgets = {
            'data_nascimento': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'aspectos_mudancas': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['matricula'].required = True
        self.fields['data_nascimento'].input_formats = ['%Y-%m-%d']
        _mascarar(self, {
            'cpf': ('cpf', '000.000.000-00', 14),
            'rg': ('numero', 'Somente números', 9),
            'contato': ('telefone', '(00) 00000-0000', 16),
        })
        _boolean_para_simnao(self)
        _compactar_textareas(self)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('cpf') and not cleaned.get('rg'):
            self.add_error('cpf', 'Informe ao menos o CPF ou o RG da criança.')
        # Zera campos dependentes quando o booleano controlador é "Não"
        # (blocos ficam ocultos no form, mas ainda são enviados no POST).
        dependentes = {
            'diagnostico': 'diagnostico_descricao',
            'sensibilidade': 'sensibilidade_descricao',
            'dificuldade_motora': 'dificuldade_motora_descricao',
            'dificuldade_emocional': 'dificuldade_emocional_descricao',
        }
        for bool_field, desc_field in dependentes.items():
            if not cleaned.get(bool_field):
                cleaned[desc_field] = ''
        if not cleaned.get('mudancas_positivas'):
            cleaned['aspectos_mudancas'] = []
            cleaned['aspectos_outros'] = ''
        return cleaned


class FamiliaForm(forms.ModelForm):
    class Meta:
        model = Familia
        exclude = ['data_criacao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ['cep', 'bairro', 'cidade']:
            self.fields[nome].required = True
        _mascarar(self, {'cep': ('cep', '00000-000', 9)})
        _boolean_para_simnao(self)
        _compactar_textareas(self)


class ResponsavelAtendidoForm(forms.ModelForm):
    class Meta:
        model = ResponsavelAtendido
        exclude = ['data_criacao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ['nome', 'parentesco', 'contato']:
            self.fields[nome].required = True
        _mascarar(self, {
            'cpf': ('cpf', '000.000.000-00', 14),
            'rg': ('numero', 'Somente números', 15),
            'contato': ('telefone', '(00) 00000-0000', 16),
            'outro_contato': ('telefone', '(00) 00000-0000', 16),
        })

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
        _boolean_para_simnao(self)
        _compactar_textareas(self)


class ListaEsperaForm(forms.ModelForm):
    class Meta:
        model = ListaEspera
        fields = (
            "nome_atendido", "data_nascimento", "nome_responsavel",
            "contato_responsavel", "renda_familiar", "quantidade_pessoas_familia",
            "parente_dentro_projeto", "observacoes",
        )
        widgets = {
            "data_nascimento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_nascimento"].input_formats = ["%Y-%m-%d"]
        _mascarar(self, {"contato_responsavel": ("telefone", "(00) 00000-0000", 16)})
        _boolean_para_simnao(self)


# Novos responsáveis são adicionados sob demanda; vínculo a existentes é feito por chips.
ResponsavelFormSet = modelformset_factory(
    ResponsavelAtendido,
    form=ResponsavelAtendidoForm,
    extra=0,
    can_delete=True,
)
