import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from voluntario.models import Grupo, LISTA_AREAS


MENCAO_USERNAME_RE = re.compile(r"(?<![\w@])@(?P<username>[\w.+-]+)", re.UNICODE)


class Reuniao(models.Model):
    titulo = models.CharField(max_length=180)
    data_reuniao = models.DateTimeField(db_index=True)
    descricao = models.TextField(blank=True)
    grupo = models.ForeignKey(
        Grupo,
        on_delete=models.PROTECT,
        related_name="reunioes",
    )

    class Meta:
        ordering = ["-data_reuniao", "titulo"]
        verbose_name = "Reunião"
        verbose_name_plural = "Reuniões"

    def __str__(self):
        return f"{self.titulo} — {self.data_reuniao:%d/%m/%Y}"


class Pauta(models.Model):
    class Status(models.TextChoices):
        A_DISCUTIR = "A_DISCUTIR", "A discutir"
        EM_DISCUSSAO = "EM_DISCUSSAO", "Em discussão"
        CONCLUIDA = "CONCLUIDA", "Concluída"

    class Prioridade(models.TextChoices):
        BAIXA = "BAIXA", "Baixa"
        MEDIA = "MEDIA", "Média"
        ALTA = "ALTA", "Alta"

    # Alias mantido para código que consumia a tupla de escolhas diretamente.
    STATUS = Status.choices
    PRIORIDADES = Prioridade.choices

    titulo = models.CharField(max_length=180)
    descricao = models.TextField()
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.A_DISCUTIR,
    )
    prioridade = models.CharField(
        max_length=10,
        choices=Prioridade.choices,
        default=Prioridade.MEDIA,
    )
    etiquetas = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de etiquetas curtas exibidas no card.",
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pautas_criadas",
    )
    responsaveis = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="pautas_sob_responsabilidade",
    )
    emitido_por_area = models.CharField(
        max_length=30,
        choices=LISTA_AREAS,
        help_text="Área do autor no momento em que a pauta foi criada.",
    )
    prazo_ddl = models.DateTimeField("prazo limite")
    grupo = models.ForeignKey(
        Grupo,
        on_delete=models.PROTECT,
        related_name="pautas",
    )
    reuniao = models.ForeignKey(
        Reuniao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pautas",
    )
    usuarios_ciencia = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="CienciaPauta",
        through_fields=("pauta", "voluntario"),
        related_name="pautas_com_ciencia",
        blank=True,
    )
    ordem = models.PositiveIntegerField(
        default=0,
        help_text="Posição do card dentro da coluna Kanban.",
    )
    ordem_reuniao = models.PositiveIntegerField(
        default=0,
        help_text="Posição da pauta no roteiro da reunião.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "ordem", "prazo_ddl", "-criado_em"]
        verbose_name = "Pauta"
        verbose_name_plural = "Pautas"

    def __init__(self, *args, **kwargs):
        # Compatibilidade com integrações antigas que ainda enviam ``ddl``.
        if "ddl" in kwargs and "prazo_ddl" not in kwargs:
            kwargs["prazo_ddl"] = kwargs.pop("ddl")
        super().__init__(*args, **kwargs)

    def __str__(self):
        return self.titulo

    def clean(self):
        super().clean()
        erros = {}

        if self.reuniao_id and self.grupo_id:
            if self.reuniao.grupo_id != self.grupo_id:
                erros["reuniao"] = "A reunião e a pauta precisam pertencer ao mesmo grupo."

        if not isinstance(self.etiquetas, list):
            erros["etiquetas"] = "As etiquetas precisam ser uma lista."
        elif any(not isinstance(etiqueta, str) or not etiqueta.strip() for etiqueta in self.etiquetas):
            erros["etiquetas"] = "Cada etiqueta precisa ser um texto não vazio."

        if erros:
            raise ValidationError(erros)

    @property
    def ddl(self):
        """Alias temporário para código legado; prefira ``prazo_ddl``."""
        return self.prazo_ddl

    @ddl.setter
    def ddl(self, valor):
        self.prazo_ddl = valor

    @property
    def status_cor(self):
        return {
            self.Status.A_DISCUTIR: "#d97706",
            self.Status.EM_DISCUSSAO: "#7c3aed",
            self.Status.CONCLUIDA: "#16845b",
        }.get(self.status, "#64748b")

    @property
    def proximo_status(self):
        return {
            self.Status.A_DISCUTIR: self.Status.EM_DISCUSSAO,
            self.Status.EM_DISCUSSAO: self.Status.CONCLUIDA,
        }.get(self.status)

    @property
    def prioridade_cor(self):
        return {
            self.Prioridade.BAIXA: "#16845b",
            self.Prioridade.MEDIA: "#d97706",
            self.Prioridade.ALTA: "#dc2626",
        }.get(self.prioridade, "#64748b")


class ComentarioPauta(models.Model):
    pauta = models.ForeignKey(
        Pauta,
        on_delete=models.CASCADE,
        related_name="comentarios",
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="comentarios_em_pautas",
    )
    texto = models.TextField(max_length=2000)
    criado_em = models.DateTimeField(auto_now_add=True)
    mencoes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="mencoes_em_comentarios",
    )

    class Meta:
        ordering = ["criado_em"]
        verbose_name = "Comentário de pauta"
        verbose_name_plural = "Comentários de pautas"

    def __str__(self):
        return f"{self.autor} em {self.pauta}"

    def usernames_mencionados(self):
        """Retorna usernames únicos na ordem em que aparecem no texto."""
        encontrados = []
        vistos = set()
        for match in MENCAO_USERNAME_RE.finditer(self.texto or ""):
            username = match.group("username")
            chave = username.casefold()
            if chave not in vistos:
                vistos.add(chave)
                encontrados.append(username)
        return encontrados

    @property
    def usuarios_mencionados(self):
        """Nome de domínio mais explícito para consultar os usuários resolvidos."""
        return self.mencoes

    def sincronizar_mencoes(self):
        usernames = self.usernames_mencionados()
        if not usernames:
            self.mencoes.clear()
            return

        consulta = Q()
        for username in usernames:
            consulta |= Q(username__iexact=username)
        usuarios = get_user_model().objects.ativos().filter(consulta)
        self.mencoes.set(usuarios)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sincronizar_mencoes()


# Nome curto oferecido pela nova API sem quebrar imports históricos.
Comentario = ComentarioPauta


class CienciaPauta(models.Model):
    pauta = models.ForeignKey(
        Pauta,
        on_delete=models.CASCADE,
        related_name="ciencias",
    )
    voluntario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ciencias_de_pautas",
    )
    ciente_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["pauta", "voluntario"],
                name="ciencia_unica_por_voluntario_e_pauta",
            ),
        ]
        verbose_name = "Ciência de pauta"
        verbose_name_plural = "Ciências de pautas"

    def __str__(self):
        return f"{self.voluntario} ciente de {self.pauta}"
