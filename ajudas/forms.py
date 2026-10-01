from django import forms

from voluntario.models import LISTA_AREAS
from .models import Ajuda
from .selectors import disponibilidades_confirmadas
from .validators import validar_destino


class RevisaoForm(forms.Form):
    revisao = forms.IntegerField(min_value=0)


class NecessidadeForm(forms.Form):
    area = forms.ChoiceField(choices=LISTA_AREAS)
    hora_inicio = forms.TimeField(input_formats=["%H:%M"])
    hora_fim = forms.TimeField(input_formats=["%H:%M"])
    quantidade = forms.IntegerField(min_value=0, max_value=100000)


class AjudaForm(forms.Form):
    voluntario = forms.IntegerField(min_value=1)
    area_destino = forms.ChoiceField(choices=LISTA_AREAS)
    hora_inicio = forms.TimeField(input_formats=["%H:%M"])
    hora_fim = forms.TimeField(input_formats=["%H:%M"])


class AjudaAdminForm(forms.ModelForm):
    revisao_escala = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = Ajuda
        fields = ["voluntario", "area_destino", "hora_inicio", "hora_fim"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["revisao_escala"].initial = self.instance.escala.revisao
            if "voluntario" in self.fields:
                ids = disponibilidades_confirmadas(self.instance.sabado).values_list("voluntario_id", flat=True)
                self.fields["voluntario"].queryset = self.fields["voluntario"].queryset.filter(pk__in=ids)

    def clean(self):
        dados = super().clean()
        if not self.instance.pk:
            return dados
        from .services import _conferir_revisao

        _conferir_revisao(self.instance.escala, dados.get("revisao_escala"))
        if self.instance.escala.status != "RASCUNHO":
            raise forms.ValidationError("Reabra a escala no quadro antes de editar uma ajuda publicada.")
        # O admin cria uma subclasse cujo Meta.fields também inclui readonlys.
        campos = AjudaAdminForm.Meta.fields
        if all(campo in dados for campo in campos):
            candidata = Ajuda(escala=self.instance.escala, **{c: dados[c] for c in campos})
            validar_destino(candidata, self.instance.escala.necessidades.all())
        # O ModelForm executa também Ajuda.clean(): presença, área própria,
        # limites do sábado e conflito com os demais registros.
        return dados
