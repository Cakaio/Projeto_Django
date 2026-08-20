from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone


@receiver(post_save, sender='supply.Pedido')
def sync_lancamento_do_pedido(sender, instance, created, **kwargs):
    """Espelha o pedido do Supply como despesa no Financeiro.

    Três coisas aqui já custaram dinheiro invisível e valem explicação:

    1. O valor lançado é o TOTAL (`valor_total` = unitário x quantidade). Antes
       era `valor`, o unitário: um pedido de 10 unidades a R$ 5 entrava como
       R$ 5 em vez de R$ 50, e o Financeiro subnotificava dez vezes.
    2. A `area` do pedido é copiada. Sem ela o gasto do Supply não contava no
       teto do Supply — e acompanhar teto por área era metade do pedido do ADM.
    3. A categoria é criada se não existir. Antes o sinal desistia em silêncio
       quando ela faltava: o pedido era salvo, o dinheiro saía e nada aparecia
       no Financeiro, sem erro nenhum para ninguém notar.
    """
    from .models import Categoria, Lancamento

    if not instance.valor:
        # Valor removido: o lançamento não tem mais o que representar.
        Lancamento.objects.filter(pedido=instance).delete()
        return

    categoria, _ = Categoria.objects.get_or_create(
        nome='Materiais Supply',
        defaults={'tipo': 'DESPESA', 'ativo': True},
    )
    if categoria.tipo != 'DESPESA' or not categoria.ativo:
        # Alguém desativou ou trocou o tipo da categoria pela tela. Corrigir na
        # mão é melhor que deixar o gasto fora do Financeiro em silêncio.
        categoria.tipo = 'DESPESA'
        categoria.ativo = True
        categoria.save(update_fields=['tipo', 'ativo'])

    valores = {
        'valor': instance.valor_total,
        'categoria': categoria,
        'area': instance.area or '',
    }

    existente = Lancamento.objects.filter(pedido=instance).first()
    if existente:
        # `update()` de propósito: não dispara save() nem sinal, e aqui só
        # mudam campos calculados a partir do pedido.
        Lancamento.objects.filter(pk=existente.pk).update(**valores)
        return

    Lancamento.objects.create(
        data=instance.sabado.data if instance.sabado else timezone.now().date(),
        descricao=f'Pedido: {instance.nome}',
        origem='SUPPLY',
        pedido=instance,
        **valores,
    )


@receiver(post_delete, sender='supply.Pedido')
def deletar_lancamento_do_pedido(sender, instance, **kwargs):
    """Remove Lancamento vinculado quando Pedido é deletado."""
    from .models import Lancamento

    Lancamento.objects.filter(pedido=instance).delete()
