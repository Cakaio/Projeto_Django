from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone


@receiver(post_save, sender='supply.Pedido')
def sync_lancamento_do_pedido(sender, instance, created, **kwargs):
    """Cria ou atualiza Lancamento de despesa quando Pedido tem valor."""
    from .models import Categoria, Lancamento

    if not instance.valor:
        # Se valor foi removido, apagar lancamento vinculado
        Lancamento.objects.filter(pedido=instance).delete()
        return

    try:
        categoria = Categoria.objects.get(
            nome='Materiais Supply', tipo='DESPESA', ativo=True
        )
    except Categoria.DoesNotExist:
        return  # ADM/FIN precisa criar a categoria antes

    if created:
        Lancamento.objects.create(
            categoria=categoria,
            valor=instance.valor,
            data=instance.sabado.data if instance.sabado else timezone.now().date(),
            descricao=f'Pedido: {instance.nome}',
            origem='SUPPLY',
            pedido=instance,
        )
    else:
        Lancamento.objects.filter(pedido=instance).update(
            valor=instance.valor,
            categoria=categoria,
        )


@receiver(post_delete, sender='supply.Pedido')
def deletar_lancamento_do_pedido(sender, instance, **kwargs):
    """Remove Lancamento vinculado quando Pedido é deletado."""
    from .models import Lancamento

    Lancamento.objects.filter(pedido=instance).delete()
