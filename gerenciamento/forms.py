import re

from django import forms
from django.contrib.auth import get_user_model

from .models import ComentarioPauta, Pauta, Reuniao
from .services import pautas_organizaveis_ao_usuario


class PautaForm(forms.ModelForm):
    etiquetas_texto = forms.CharField(
        required=False,
        label="Etiquetas",
        help_text="Separe por vírgulas (até 8 etiquetas).",
        widget=forms.TextInput(attrs={
            "class": "field-control",
            "placeholder": "ex.: orçamento, evento, urgente",
            "autocomplete": "off",
        }),
    )

    class Meta:
        model = Pauta
        fields = [
            "titulo",
            "descricao",
            "status",
            "prioridade",
            "prazo_ddl",
            "grupo",
            "reuniao",
            "responsaveis",
            "etiquetas_texto",
        ]
        labels = {
            "titulo": "Título",
            "descricao": "Descrição",
            "prazo_ddl": "Prazo limite (DDL)",
            "status": "Status",
            "prioridade": "Prioridade",
            "grupo": "Grupo direcionado",
            "reuniao": "Reunião (opcional)",
            "responsaveis": "Responsáveis (opcional)",
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
            "prazo_ddl": forms.DateTimeInput(attrs={
                "class": "field-control",
                "type": "datetime-local",
            }, format="%Y-%m-%dT%H:%M"),
            "grupo": forms.Select(attrs={"class": "field-control"}),
            "reuniao": forms.Select(attrs={"class": "field-control"}),
            "responsaveis": forms.SelectMultiple(attrs={
                "class": "field-control",
                "size": 5,
            }),
            "status": forms.Select(attrs={"class": "field-control"}),
            "prioridade": forms.Select(attrs={"class": "field-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["prazo_ddl"].input_formats = ("%Y-%m-%dT%H:%M",)
        self.fields["responsaveis"].queryset = (
            get_user_model().objects.ativos().order_by("first_name", "last_name", "username")
        )
        self.fields["responsaveis"].help_text = (
            "Use Ctrl (Windows) ou Command (macOS) para selecionar várias pessoas."
        )
        self.fields["reuniao"].queryset = Reuniao.objects.select_related("grupo")
        if self.instance and self.instance.pk:
            self.initial["etiquetas_texto"] = ", ".join(self.instance.etiquetas or [])

    def clean_etiquetas_texto(self):
        texto = self.cleaned_data.get("etiquetas_texto") or ""
        etiquetas = []
        vistas = set()
        for parte in re.split(r"[,;]", texto):
            etiqueta = " ".join(parte.split()).strip()
            if not etiqueta:
                continue
            if len(etiqueta) > 30:
                raise forms.ValidationError("Cada etiqueta pode ter no máximo 30 caracteres.")
            chave = etiqueta.casefold()
            if chave not in vistas:
                vistas.add(chave)
                etiquetas.append(etiqueta)
        if len(etiquetas) > 8:
            raise forms.ValidationError("Use no máximo 8 etiquetas.")
        return etiquetas

    def clean(self):
        cleaned_data = super().clean()
        grupo = cleaned_data.get("grupo")
        reuniao = cleaned_data.get("reuniao")
        responsaveis = cleaned_data.get("responsaveis")

        if reuniao and grupo and reuniao.grupo_id != grupo.pk:
            self.add_error("reuniao", "Escolha uma reunião do mesmo grupo da pauta.")
        if responsaveis is not None and grupo:
            membros_ids = set(grupo.voluntarios().values_list("pk", flat=True))
            fora_do_grupo = [
                usuario for usuario in responsaveis if usuario.pk not in membros_ids
            ]
            if fora_do_grupo:
                self.add_error(
                    "responsaveis",
                    "Todos os responsáveis precisam ser integrantes ativos do grupo.",
                )

        self.instance.etiquetas = cleaned_data.get("etiquetas_texto") or []
        return cleaned_data


class ReuniaoForm(forms.ModelForm):
    pautas_ids = forms.CharField(
        widget=forms.HiddenInput(attrs={"data-pautas-selecionadas": ""}),
        required=False,
    )

    class Meta:
        model = Reuniao
        fields = ["titulo", "data_reuniao", "descricao", "grupo", "pautas_ids"]
        labels = {
            "titulo": "Título",
            "data_reuniao": "Data e hora",
            "descricao": "Contexto da reunião (opcional)",
            "grupo": "Grupo",
        }
        widgets = {
            "titulo": forms.TextInput(attrs={
                "class": "field-control",
                "placeholder": "ex.: Alinhamento mensal",
                "autocomplete": "off",
            }),
            "data_reuniao": forms.DateTimeInput(attrs={
                "class": "field-control",
                "type": "datetime-local",
            }, format="%Y-%m-%dT%H:%M"),
            "descricao": forms.Textarea(attrs={
                "class": "field-control",
                "rows": 3,
                "placeholder": "Objetivo, participantes ou instruções para a apresentação…",
            }),
            "grupo": forms.Select(attrs={"class": "field-control", "data-grupo-reuniao": ""}),
        }

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_reuniao"].input_formats = ("%Y-%m-%dT%H:%M",)
        self.pautas_disponiveis = (
            pautas_organizaveis_ao_usuario(usuario)
            .filter(reuniao__isnull=True)
            .select_related("grupo")
            .prefetch_related("responsaveis")
            .order_by("grupo__nome", "status", "ordem", "prazo_ddl")
            if usuario is not None
            else Pauta.objects.none()
        )
        self.pautas_selecionadas = []

    def clean_pautas_ids(self):
        valor = self.cleaned_data.get("pautas_ids") or ""
        ids = []
        for parte in valor.split(","):
            parte = parte.strip()
            if not parte:
                continue
            if not parte.isdigit():
                raise forms.ValidationError("A seleção de pautas é inválida.")
            identificador = int(parte)
            if identificador not in ids:
                ids.append(identificador)

        if not ids:
            raise forms.ValidationError("Adicione ao menos uma pauta à reunião.")

        encontradas = {
            pauta.pk: pauta
            for pauta in self.pautas_disponiveis.filter(pk__in=ids)
        }
        if len(encontradas) != len(ids):
            raise forms.ValidationError(
                "Uma das pautas selecionadas não está mais disponível."
            )
        self.pautas_selecionadas = [encontradas[pk] for pk in ids]
        return ",".join(str(pk) for pk in ids)

    def clean(self):
        cleaned_data = super().clean()
        grupo = cleaned_data.get("grupo")
        if grupo and self.pautas_selecionadas and any(
            pauta.grupo_id != grupo.pk for pauta in self.pautas_selecionadas
        ):
            self.add_error(
                "pautas_ids",
                "Todas as pautas precisam pertencer ao grupo da reunião.",
            )
        return cleaned_data


class ComentarioPautaForm(forms.ModelForm):
    class Meta:
        model = ComentarioPauta
        fields = ["texto"]
        labels = {"texto": "Adicionar comentário"}
        widgets = {
            "texto": forms.Textarea(attrs={
                "class": "comment-input",
                "rows": 3,
                "placeholder": "Comente e use @usuario para mencionar alguém…",
                "autocomplete": "off",
            }),
        }
