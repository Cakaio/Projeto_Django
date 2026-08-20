"""Espelha cada contribuição como um lançamento de RECEITA no Financeiro.

Como `Lancamento.save()` copia o tipo da categoria, basta apontar para uma
categoria de RECEITA para a doação aparecer sozinha no fluxo de caixa e no DRE
(que agrupa por `categoria__nome`) — sem tocar no código do app `adm`.

Para importar histórico SEM gerar lançamento (evitando contar receita em
dobro), marque a instância antes de salvar:

    contribuicao.pular_lancamento = True
    contribuicao.save()
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import CATEGORIA_DOACOES, Contribuicao


def _categoria_doacoes():
    from adm.models import Categoria
    categoria, _ = Categoria.objects.get_or_create(
        nome=CATEGORIA_DOACOES,
        defaults={'tipo': 'RECEITA', 'ativo': True},
    )
    return categoria


def _descricao(contribuicao):
    texto = f'Doação de {contribuicao.parceiro.nome} — {contribuicao.competencia:%m/%Y}'
    if contribuicao.parceiro.responsavel_id:
        texto += f' (carteira de {contribuicao.parceiro.responsavel.get_full_name() or contribuicao.parceiro.responsavel.username})'
    return texto


@receiver(post_save, sender=Contribuicao)
def sincronizar_lancamento(sender, instance, **kwargs):
    if getattr(instance, 'pular_lancamento', False):
        return

    from adm.models import Lancamento

    if instance.lancamento_id:
        # Mantém o lançamento existente alinhado (valor/data podem ser corrigidos).
        Lancamento.objects.filter(pk=instance.lancamento_id).update(
            valor=instance.valor,
            data=instance.data_recebimento,
            descricao=_descricao(instance),
            # A conta pode ter sido corrigida depois ("caiu no BB, não no Caju").
            conta_id=instance.conta_id,
        )
        return

    lancamento = Lancamento.objects.create(
        categoria=_categoria_doacoes(),
        valor=instance.valor,
        data=instance.data_recebimento,      # data do crédito, não "hoje"
        descricao=_descricao(instance),
        origem='DOACAO',
        criado_por=instance.registrado_por,
        # Sem copiar a conta, o saldo do cartão/banco ignoraria a doação.
        conta_id=instance.conta_id,
    )
    # `update()` não dispara post_save — evita recursão infinita.
    Contribuicao.objects.filter(pk=instance.pk).update(lancamento=lancamento)
    instance.lancamento_id = lancamento.pk


@receiver(post_delete, sender=Contribuicao)
def remover_lancamento(sender, instance, **kwargs):
    if instance.lancamento_id:
        from adm.models import Lancamento
        Lancamento.objects.filter(pk=instance.lancamento_id).delete()
