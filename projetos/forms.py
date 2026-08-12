from django import forms
from django.db.models import Q

from voluntario.models import Voluntario

from .models import Demanda, RegistroDemanda


def _voluntarios_ativos():
    """Quem está no projeto hoje.

    Oferecer quem já saiu enche a lista de gente que não dá para cobrar nem
    procurar — e é para cobrar e procurar que estes dois campos existem.
    """
    return Voluntario.objects.ativos().order_by('first_name', 'username')


class DemandaForm(forms.ModelForm):

    class Meta:
        model = Demanda
        fields = ['titulo', 'area', 'o_que_pediram', 'o_que_fizemos', 'status',
                  'retorno', 'prioridade', 'responsavel', 'contato_na_area',
                  'entregue_em']
        widgets = {
            'o_que_pediram': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Nas palavras da área: o que eles pediram?'}),
            'o_que_fizemos': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'O que já está no ar para eles?'}),
            'entregue_em': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entregue_em'].input_formats = ['%Y-%m-%d']
        for campo in ('responsavel', 'contato_na_area'):
            queryset = _voluntarios_ativos()
            # Quem já está preenchido continua na lista mesmo se tiver saído do
            # projeto. Sem isso, uma demanda cujo responsável foi desligado fica
            # IMPOSSÍVEL de editar — nem para mudar o status — até alguém
            # esvaziar o campo, e esvaziar apaga do registro quem cuidava dela
            # na época. O objetivo da regra era melhorar a lista de escolha, não
            # travar a edição e comer histórico.
            atual = getattr(self.instance, f'{campo}_id', None)
            if atual:
                queryset = (Voluntario.objects
                            .filter(Q(pk__in=queryset.values('pk')) | Q(pk=atual))
                            .order_by('first_name', 'last_name', 'username'))
            self.fields[campo].queryset = queryset
        self.fields['responsavel'].empty_label = 'Ninguém ainda'
        self.fields['contato_na_area'].empty_label = 'Ainda não falamos com ninguém'
        self.fields['titulo'].widget.attrs['placeholder'] = 'O que é, em uma linha'
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')


class RegistroDemandaForm(forms.ModelForm):
    """O histórico. `autor` não está aqui de propósito: sai de `request.user`."""

    class Meta:
        model = RegistroDemanda
        fields = ['data', 'tipo', 'descricao']
        widgets = {
            'data': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'descricao': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'O que aconteceu? Com quem falamos, o que ficou combinado.'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data'].input_formats = ['%Y-%m-%d']
        for campo in self.fields.values():
            campo.widget.attrs.setdefault('class', 'pcf-input')
