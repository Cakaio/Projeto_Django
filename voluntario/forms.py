from django.contrib.auth.forms import PasswordChangeForm

class AlterarSenhaForm(PasswordChangeForm):
    pass
from django import forms
from .models import Voluntario

class MeuPerfilForm(forms.ModelForm):
    class Meta:
        model = Voluntario
        fields = [
            "username",      # bloqueado
            "area",          # bloqueado
            "first_name",
            "last_name",
            "apelido",
            "email",
            "celular",
            "instagram",
            "endereco",
            "republica",
            "data_nascimento",
            "alergia",
            "restricao_alimentar",
            "medicacao_continua",
            "alimentacao",
            "curso",
            "faculdade",
            "foto",
            "rg",
            "email_alternativo",
            "talentos",
        ]
        widgets = {
            "data_nascimento": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "celular": forms.TextInput(attrs={"class": "form-control", "placeholder": "(99) 99999-9999"}),
            "instagram": forms.TextInput(attrs={"class": "form-control", "placeholder": "@usuario"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 512 campos bloqueados
        self.fields["username"].disabled = True
        self.fields["area"].disabled = True

        # Destacar campos obrigatórios
        for name, field in self.fields.items():
            if field.required:
                field.widget.attrs["class"] = field.widget.attrs.get("class", "") + " required-field"

    def clean_celular(self):
        celular = self.cleaned_data.get("celular")
        if celular:
            import re
            pattern = r"^\(\d{2}\) \d{4,5}-\d{4}$"
            if not re.match(pattern, celular):
                raise forms.ValidationError("Informe o telefone no formato (99) 99999-9999")
        return celular

    def clean_instagram(self):
        instagram = self.cleaned_data.get("instagram")
        if instagram and not instagram.startswith("@"): 
            raise forms.ValidationError("O Instagram deve começar com @")
        return instagram
