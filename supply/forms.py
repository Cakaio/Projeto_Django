from django import forms
from django.forms import modelformset_factory
from .models import Item, Pedido
from semanario.models import Material


class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = [
            "item",
            "especificar",
            "link",
            "quantidade",
            "unidade",
            "sabado",
            "area",
        ]
        widgets = {
            "item": forms.Select(attrs={"class": "form-control"}),
            "especificar": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Ex.: cor, tamanho, marca ou outra observação"
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Item.objects.filter(ativo=True).order_by("nome")


PedidoFormSet = modelformset_factory(
    Pedido,
    form=PedidoForm,
    extra=1,
    can_delete=False
)

class MeuPedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ["item", "especificar", "link", "quantidade", "unidade", "sabado", "area"]
        widgets = {
            "item": forms.Select(attrs={"class": "form-control"}),
            "especificar": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Cor, tamanho, marca ou observação"}),
            "link": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://exemplo.com/imagem.jpg"}),
            "quantidade": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "unidade": forms.Select(attrs={"class": "form-control"}),
            "sabado": forms.Select(attrs={"class": "form-control"}),
            "area": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Item.objects.filter(ativo=True).order_by("nome")


class MeuMaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ["item", "especificar", "link", "quantidade", "unidade", "pedido", "local"]
        widgets = {
            "item": forms.Select(attrs={"class": "form-control"}),
            "especificar": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Cor, tamanho, marca ou observação"}),
            "link": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://exemplo.com/imagem.jpg"}),
            "quantidade": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "unidade": forms.Select(attrs={"class": "form-control"}),
            "pedido": forms.Select(attrs={"class": "form-control"}),
            "local": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Item.objects.filter(ativo=True).order_by("nome")
