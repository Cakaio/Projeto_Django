from django import forms

from .models import ComentarioPauta, Pauta


class PautaForm(forms.ModelForm):
    class Meta:
        model = Pauta
        fields = ["titulo", "descricao", "status", "ddl", "grupo"]
        labels = {
            "titulo": "Título",
            "descricao": "Descrição",
            "ddl": "Prazo",
            "status": "Status",
            "grupo": "Grupo direcionado",
        }
        widgets = {
            "titulo": forms.TextInput(attrs={
                "class": "field-control",
                "placeholder": "O que precisa entrar em pauta?",
                "autocomplete": "off",
            }),
            "descricao": forms.Textarea(attrs={
                "class": "field-control",
                "rows": 7,
                "placeholder": "Contexto, objetivo e informações necessárias…",
            }),
            "ddl": forms.DateTimeInput(attrs={
                "class": "field-control",
                "type": "datetime-local",
            }, format="%Y-%m-%dT%H:%M"),
            "grupo": forms.Select(attrs={"class": "field-control"}),
            "status": forms.Select(attrs={"class": "field-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ddl"].input_formats = ("%Y-%m-%dT%H:%M",)


class ComentarioPautaForm(forms.ModelForm):
    class Meta:
        model = ComentarioPauta
        fields = ["texto"]
        labels = {"texto": "Adicionar comentário"}
        widgets = {
            "texto": forms.Textarea(attrs={
                "class": "comment-input",
                "rows": 2,
                "placeholder": "Escreva uma atualização ou observação…",
            }),
        }
