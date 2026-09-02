from django import forms

from voluntario.models import Voluntario

from .models import Colecao, Documento

# Um documento de postulação costuma ser PDF, foto da ficha ou carta digitada.
# A lista é fechada porque upload livre num acervo aberto a todo voluntário é
# porta para arquivo que ninguém deveria estar servindo.
EXTENSOES_ACEITAS = ('pdf', 'jpg', 'jpeg', 'png', 'webp', 'doc', 'docx', 'odt')
TAMANHO_MAXIMO_MB = 15


class ColecaoForm(forms.ModelForm):
    class Meta:
        model = Colecao
        fields = ['nome', 'descricao', 'ordem', 'ativo']
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if not isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs.setdefault('class', 'pcf-input')


class DocumentoForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = ['colecao', 'titulo', 'arquivo', 'ano', 'pessoa', 'nome_avulso',
                  'cargo_pretendido', 'resultado', 'descricao']
        widgets = {
            'descricao': forms.Textarea(attrs={'rows': 3}),
            'ano': forms.NumberInput(attrs={'min': 1990, 'max': 2100}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['colecao'].queryset = Colecao.objects.filter(ativo=True)
        self.fields['colecao'].empty_label = 'Escolha a coleção'

        # Aqui NÃO se filtra por `ativos()`. O acervo é sobre quem postulou na
        # época: quem saiu do projeto é justamente o caso mais comum de
        # documento antigo, e some da lista significaria não conseguir
        # cadastrar o documento dessa pessoa.
        self.fields['pessoa'].queryset = Voluntario.objects.order_by(
            'first_name', 'last_name', 'username')
        self.fields['pessoa'].empty_label = 'Não está cadastrado'
        self.fields['resultado'].required = False

        for nome, campo in self.fields.items():
            if isinstance(campo.widget, forms.CheckboxInput):
                continue
            campo.widget.attrs.setdefault('class', 'pcf-input')
            # O combo de busca do projeto (static/js/pcf-combo.js) transforma
            # select em campo que filtra ao digitar.
            if nome in ('colecao', 'pessoa'):
                campo.widget.attrs['data-combo'] = '1'

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if not arquivo:
            return arquivo

        nome = (getattr(arquivo, 'name', '') or '').lower()
        extensao = nome.rsplit('.', 1)[-1] if '.' in nome else ''
        if extensao not in EXTENSOES_ACEITAS:
            raise forms.ValidationError(
                'Formato não aceito. Envie PDF, imagem (JPG, PNG, WEBP) '
                'ou documento de texto (DOC, DOCX, ODT).'
            )

        tamanho = getattr(arquivo, 'size', 0) or 0
        if tamanho > TAMANHO_MAXIMO_MB * 1024 * 1024:
            raise forms.ValidationError(
                f'Arquivo muito grande ({tamanho / 1048576:.1f} MB). '
                f'O limite é {TAMANHO_MAXIMO_MB} MB.'
            )
        return arquivo
