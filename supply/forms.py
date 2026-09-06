from django import forms
from django.forms import modelformset_factory

from semanario.models import Material

from .models import Item, Local, Pedido


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            "nome",
            "descricao",
            "categoria",
            "unidade",
            "quantidade_minima",
            "ativo",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={
                "class": "pcf-input",
                "placeholder": "Ex.: Cartolina colorida",
                "autofocus": True,
            }),
            "descricao": forms.Textarea(attrs={
                "class": "pcf-input",
                "rows": 4,
                "placeholder": "Detalhes que ajudem a identificar o item",
            }),
            "categoria": forms.Select(attrs={"class": "pcf-input"}),
            "unidade": forms.Select(attrs={"class": "pcf-input"}),
            "quantidade_minima": forms.NumberInput(attrs={
                "class": "pcf-input",
                "step": "0.01",
                "min": "0",
            }),
            "ativo": forms.CheckboxInput(attrs={"class": "supply-form-checkbox"}),
        }


class LocalForm(forms.ModelForm):
    class Meta:
        model = Local
        fields = [
            "nome",
            "tipo",
            "localizacao",
            "cidade",
            "numero_contato",
            "whatsapp",
            "email",
            "site",
            "observacoes",
            "ativo",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={
                "class": "pcf-input",
                "placeholder": "Ex.: Papelaria Central",
                "autofocus": True,
            }),
            "tipo": forms.Select(attrs={"class": "pcf-input"}),
            "localizacao": forms.TextInput(attrs={
                "class": "pcf-input",
                "placeholder": "Rua, número, bairro ou referência",
            }),
            "cidade": forms.TextInput(attrs={
                "class": "pcf-input",
                "placeholder": "Ex.: São Paulo",
            }),
            "numero_contato": forms.TextInput(attrs={
                "class": "pcf-input",
                "placeholder": "(00) 00000-0000",
            }),
            "whatsapp": forms.CheckboxInput(attrs={"class": "supply-form-checkbox"}),
            "email": forms.EmailInput(attrs={
                "class": "pcf-input",
                "placeholder": "contato@exemplo.com",
            }),
            "site": forms.URLInput(attrs={
                "class": "pcf-input",
                "placeholder": "https://exemplo.com",
            }),
            "observacoes": forms.Textarea(attrs={
                "class": "pcf-input",
                "rows": 4,
                "placeholder": "Horários, condições de compra ou outras informações",
            }),
            "ativo": forms.CheckboxInput(attrs={"class": "supply-form-checkbox"}),
        }


class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = [
            "item",
            "especificar",
            "link",
            "quantidade",
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
        fields = ["item", "especificar", "link", "quantidade", "sabado", "area"]
        widgets = {
            "item": forms.Select(attrs={"class": "form-control"}),
            "especificar": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Cor, tamanho, marca ou observação"}),
            "link": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://exemplo.com/imagem.jpg"}),
            "quantidade": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "sabado": forms.Select(attrs={"class": "form-control"}),
            "area": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Item.objects.filter(ativo=True).order_by("nome")


class MeuMaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ["item", "especificar", "link", "quantidade", "pedido", "local"]
        widgets = {
            "item": forms.Select(attrs={"class": "form-control"}),
            "especificar": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Cor, tamanho, marca ou observação"}),
            "link": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://exemplo.com/imagem.jpg"}),
            "quantidade": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "pedido": forms.Select(attrs={"class": "form-control"}),
            "local": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Item.objects.filter(ativo=True).order_by("nome")
