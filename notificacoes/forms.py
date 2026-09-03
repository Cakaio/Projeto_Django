from django import forms
from voluntario.models import LISTA_AREAS

from .models import Aviso


class AvisoForm(forms.ModelForm):
    # LISTA_AREAS vem de voluntario.models de propósito: a tupla já foi
    # duplicada demais neste projeto. As salas estão lá dentro — não existe
    # lista separada de salas para voluntário.
    alvo = forms.ChoiceField(
        choices=[("", "—")] + list(LISTA_AREAS),
        required=False,
        label="Área ou sala",
    )

    class Meta:
        model = Aviso
        fields = ("titulo", "mensagem", "destino", "alvo")
        labels = {
            "titulo": "Título",
            "mensagem": "Mensagem",
            "destino": "Enviar para",
        }
        help_texts = {
            "titulo": "Até 80 caracteres — o Android trunca notificação longa.",
            "mensagem": "Até 300 caracteres — o iPhone mostra cerca de 4 linhas.",
        }

    def clean(self):
        dados = super().clean()
        if dados.get("destino") == "AREA" and not dados.get("alvo"):
            self.add_error("alvo", "Escolha a área ou sala que vai receber o aviso.")
        if dados.get("destino") == "TODOS":
            dados["alvo"] = ""
        return dados
