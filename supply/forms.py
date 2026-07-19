from django import forms
from django.forms import modelformset_factory
from .models import Pedido


class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = [
            "nome",
            "link",
            "quantidade",
            "unidade",
            "sabado",
            "area",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ex.: Cola branca"
            }),
            "link": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://exemplo.com/imagem.jpg"
            }),
            "quantidade": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0"
            }),
            "unidade": forms.Select(attrs={
                "class": "form-control"
            }),
            "sabado": forms.Select(attrs={
                "class": "form-control"
            }),
            "area": forms.Select(attrs={
                "class": "form-control"
            }),
        }

    def clean_nome(self):
        nome = self.cleaned_data.get("nome")
        if nome:
            return nome.strip()
        return nome


PedidoFormSet = modelformset_factory(
    Pedido,
    form=PedidoForm,
    extra=1,
    can_delete=False
)

class MeuPedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ["nome", "link", "quantidade", "unidade", "sabado", "area"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: Cola branca"}),
            "link": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://exemplo.com/imagem.jpg"}),
            "quantidade": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "unidade": forms.Select(attrs={"class": "form-control"}),
            "sabado": forms.Select(attrs={"class": "form-control"}),
            "area": forms.Select(attrs={"class": "form-control"}),
        }
