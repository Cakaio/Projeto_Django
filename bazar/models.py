"""Bazar: distribuição de roupas por pontos, no lugar de ficha ou dinheiro fictício.

Três decisões moldam tudo aqui, e todas vieram da liderança:

1. NÃO EXISTE CADASTRO DE PARTICIPANTE. O Bazar aponta para o `Atendido` que o
   projeto já mantém — nome, salinha, data de nascimento e até a numeração de
   camisa, calça e calçado. Recadastrar criaria duas verdades sobre a mesma
   criança e trabalho no dia do evento.

2. A TROCA DE ETAPA É MANUAL. O PRD falava em 8h45–11h e 11h–12h15, mas evento
   atrasa: se o relógio virasse sozinho às 11h com a fila da primeira etapa
   ainda andando, o sistema passaria a liberar retirada extra para quem nem foi
   atendido, e ninguém perceberia na hora.

3. A SEGUNDA ETAPA NÃO TEM LIMITE DE PONTOS. Ali o objetivo deixa de ser
   racionar e passa a ser esvaziar o estoque, então o sistema vira contador de
   peças. A validação de saldo só existe na primeira etapa.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from atendido.models import LISTA_SALAS


class Bazar(models.Model):
    """Uma edição do Bazar. Tudo que acontece no dia pendura aqui."""

    class Etapa(models.TextChoices):
        NAO_COMECOU = "NAO_COMECOU", "Ainda não começou"
        PRIMEIRA = "PRIMEIRA", "1ª etapa — cota de pontos"
        SEGUNDA = "SEGUNDA", "2ª etapa — livre, sem pontos"
        ENCERRADO = "ENCERRADO", "Encerrado"

    nome = models.CharField(max_length=120, help_text="Ex.: Bazar 2026")
    data = models.DateField(default=timezone.localdate)

    etapa = models.CharField(
        max_length=12, choices=Etapa.choices, default=Etapa.NAO_COMECOU,
        help_text="A coordenação vira a chave na hora certa. Não muda sozinho.",
    )

    cota_inicial = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        help_text="Pontos que cada atendido recebe na 1ª etapa.",
    )

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bazares_criados")
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-data", "-pk"]
        verbose_name = "Bazar"
        verbose_name_plural = "Bazares"

    def __str__(self):
        return f"{self.nome} ({self.data:%d/%m/%Y})"

    @property
    def esta_aberto(self):
        return self.etapa in (self.Etapa.PRIMEIRA, self.Etapa.SEGUNDA)

    @property
    def desconta_pontos(self):
        """Só a 1ª etapa consome cota. Na 2ª o sistema só conta peças."""
        return self.etapa == self.Etapa.PRIMEIRA

    @classmethod
    def em_andamento(cls):
        """O Bazar que a tela de atendimento deve usar agora.

        Só pode haver um aberto por vez — é o que evita duas telas registrando
        em edições diferentes no mesmo dia.
        """
        return cls.objects.filter(
            etapa__in=(cls.Etapa.PRIMEIRA, cls.Etapa.SEGUNDA)).first()

    def clean(self):
        super().clean()
        if self.esta_aberto:
            outros = Bazar.objects.filter(
                etapa__in=(self.Etapa.PRIMEIRA, self.Etapa.SEGUNDA))
            if self.pk:
                outros = outros.exclude(pk=self.pk)
            if outros.exists():
                raise ValidationError({
                    "etapa": "Já existe um Bazar aberto. Encerre o outro antes.",
                })


class Categoria(models.Model):
    """Uma categoria de peça e quanto ela custa em pontos.

    O valor é GLOBAL — a mesma camiseta vale o mesmo em qualquer sala. Foi
    decisão do PRD, e simplifica a conferência: o voluntário não precisa saber
    em que sala está para saber o preço.

    Não existe cadastro de peça individual. Cadastrar cada camiseta faria a fila
    parar; o sistema trabalha por categoria e quantidade.
    """
    bazar = models.ForeignKey(Bazar, on_delete=models.CASCADE,
                              related_name="categorias")
    nome = models.CharField(max_length=60)
    pontos = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Quantos pontos uma peça desta categoria custa.")
    estoque_inicial = models.PositiveIntegerField(
        default=0, help_text="Quantas peças entraram no Bazar. 0 = não controlado.")
    ordem = models.PositiveSmallIntegerField(
        default=0, help_text="Ordem dos botões na tela de atendimento.")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["bazar", "nome"],
                                    name="categoria_unica_por_bazar"),
        ]
        verbose_name = "Categoria de peça"
        verbose_name_plural = "Categorias de peça"

    def __str__(self):
        return f"{self.nome} — {self.pontos} ponto{'s' if self.pontos != 1 else ''}"

    @property
    def distribuido(self):
        """Peças já entregues desta categoria, somando as duas etapas."""
        return self.itens.filter(
            retirada__finalizada_em__isnull=False
        ).aggregate(total=Sum("quantidade"))["total"] or 0

    @property
    def restante(self):
        if not self.estoque_inicial:
            return None       # categoria sem controle de estoque
        return self.estoque_inicial - self.distribuido

    @property
    def estoque_baixo(self):
        restante = self.restante
        if restante is None:
            return False
        return restante <= max(3, self.estoque_inicial // 10)


class Retirada(models.Model):
    """Uma passagem do atendido pela conferência.

    Nasce em rascunho e só vale quando `finalizada_em` é preenchido. Rascunho
    não desconta ponto nem baixa estoque: se o voluntário desistir no meio, ou
    a tela cair, nada foi consumido.
    """

    class Etapa(models.TextChoices):
        PRIMEIRA = "PRIMEIRA", "1ª etapa"
        SEGUNDA = "SEGUNDA", "2ª etapa"

    class RetiradoPor(models.TextChoices):
        ATENDIDO = "ATENDIDO", "O próprio atendido"
        PAI_MAE = "PAI_MAE", "Pai ou mãe"
        RESPONSAVEL = "RESPONSAVEL", "Responsável cadastrado"
        OUTRO = "OUTRO", "Outra pessoa autorizada"

    bazar = models.ForeignKey(Bazar, on_delete=models.PROTECT,
                              related_name="retiradas")
    atendido = models.ForeignKey("atendido.Atendido", on_delete=models.PROTECT,
                                 related_name="retiradas_no_bazar")
    etapa = models.CharField(max_length=10, choices=Etapa.choices)

    # Qual das salas físicas do Bazar atendeu. Serve para achar a origem de uma
    # divergência depois do evento.
    sala_do_bazar = models.CharField(
        max_length=30, blank=True,
        help_text="Sala física da conferência. Ex.: Sala 1.")

    conferido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="retiradas_conferidas")

    retirado_por = models.CharField(
        max_length=12, choices=RetiradoPor.choices, default=RetiradoPor.ATENDIDO,
        help_text="Quem levou a sacola. O atendido nem sempre está presente.")
    retirado_por_nome = models.CharField(
        max_length=120, blank=True,
        help_text="Nome de quem levou, quando não é o próprio atendido.")

    # Cópia da cota do momento. Se a coordenação mudar a cota no meio do evento,
    # o histórico de quem já passou não pode ser reescrito.
    cota_no_momento = models.PositiveSmallIntegerField(default=0)

    criado_em = models.DateTimeField(default=timezone.now)
    finalizada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em", "-pk"]
        constraints = [
            # Uma retirada FINALIZADA por atendido por etapa. É a trava contra
            # passar duas vezes pela fila. Rascunhos não entram: `condition`
            # limita a regra ao que já foi concluído.
            models.UniqueConstraint(
                fields=["bazar", "atendido", "etapa"],
                condition=models.Q(finalizada_em__isnull=False),
                name="uma_retirada_finalizada_por_etapa",
            ),
        ]
        verbose_name = "Retirada"
        verbose_name_plural = "Retiradas"

    def __str__(self):
        return f"{self.atendido.nome} — {self.get_etapa_display()}"

    @property
    def pontos_usados(self):
        return self.itens.aggregate(
            total=Sum("pontos_total"))["total"] or 0

    @property
    def total_pecas(self):
        return self.itens.aggregate(
            total=Sum("quantidade"))["total"] or 0

    @property
    def esta_finalizada(self):
        return self.finalizada_em is not None


class ItemRetirada(models.Model):
    """Quantas peças de uma categoria saíram nesta retirada.

    `pontos_unitarios` é cópia, não referência: se a coordenação corrigir o
    valor de "Calça" no meio do Bazar, o que já foi entregue continua valendo o
    que valia na hora. Sem isso, o relatório do fim do dia contaria história
    diferente da que aconteceu.
    """
    retirada = models.ForeignKey(Retirada, on_delete=models.CASCADE,
                                 related_name="itens")
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT,
                                  related_name="itens")
    quantidade = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)])
    pontos_unitarios = models.PositiveSmallIntegerField()
    pontos_total = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["retirada", "categoria"],
                                    name="uma_linha_por_categoria_na_retirada"),
        ]
        verbose_name = "Item da retirada"
        verbose_name_plural = "Itens da retirada"

    def __str__(self):
        return f"{self.categoria.nome} × {self.quantidade}"

    def save(self, *args, **kwargs):
        if not self.pontos_unitarios:
            self.pontos_unitarios = self.categoria.pontos
        self.pontos_total = self.pontos_unitarios * self.quantidade
        super().save(*args, **kwargs)
