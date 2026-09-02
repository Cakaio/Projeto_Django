from django import forms

from .models import Asset, Documento

EXTENSOES_DE_IMAGEM = ('jpg', 'jpeg', 'png', 'webp', 'gif', 'svg')
TAMANHO_MAXIMO_MB = 8


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ['titulo', 'tipo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Revista não entra aqui: documento de revista nasce pelo botão
        # "gerar layout" da própria revista, que já sabe qual é.
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')


class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = ['nome', 'categoria', 'arquivo', 'apelido']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['apelido'].required = False
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if not arquivo:
            return arquivo

        nome = (getattr(arquivo, 'name', '') or '').lower()
        extensao = nome.rsplit('.', 1)[-1] if '.' in nome else ''
        if extensao not in EXTENSOES_DE_IMAGEM:
            raise forms.ValidationError(
                'Envie imagem: JPG, PNG, WEBP, GIF ou SVG.')

        tamanho = getattr(arquivo, 'size', 0) or 0
        if tamanho > TAMANHO_MAXIMO_MB * 1024 * 1024:
            raise forms.ValidationError(
                f'Imagem muito grande ({tamanho / 1048576:.1f} MB). '
                f'O limite é {TAMANHO_MAXIMO_MB} MB — exporte do Canva em PNG comprimido.')
        return arquivo

    def clean_apelido(self):
        """Apelido vazio precisa virar None, não string vazia.

        `SlugField(unique=True, blank=True)` deixa gravar '' — e o segundo
        asset sem apelido colide com o primeiro por unicidade.
        """
        return self.cleaned_data.get('apelido') or None
