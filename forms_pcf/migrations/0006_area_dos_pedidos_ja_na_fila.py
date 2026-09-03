"""Preenche a área dos pedidos de reembolso que ficaram sem ela.

A área do pedido só era gravada no momento do pagamento, então todo pedido em
aberto aparecia na fila da ADM como "Sem área nem evento" — e a pessoa que
registrava o pagamento tinha que escolher a área na mão, toda vez, adivinhando
de quem era o gasto.

A área sai do solicitante, que é de onde ela deveria ter saído desde o começo.

Só mexe em pedido SEM lançamento. Pedido que já virou lançamento já entrou no
teto de alguma área (ou de nenhuma, por decisão de quem pagou), e reatribuir
dinheiro já contabilizado mudaria número fechado do financeiro — isso é decisão
da ADM, não de uma migração.
"""
from django.db import migrations


def puxar_a_area_do_solicitante(apps, schema_editor):
    PedidoReembolso = apps.get_model('forms_pcf', 'PedidoReembolso')
    pendentes = (PedidoReembolso.objects
                 .filter(area='', evento__isnull=True, lancamento__isnull=True)
                 .select_related('solicitante'))
    for pedido in pendentes:
        area = getattr(pedido.solicitante, 'area', '') or ''
        if area:
            pedido.area = area
            pedido.save(update_fields=['area'])


def nao_da_para_desfazer(apps, schema_editor):
    """Voltar teria que distinguir a área preenchida aqui da que a ADM
    escolheu à mão, e o banco não guarda essa diferença."""


class Migration(migrations.Migration):

    dependencies = [
        ('forms_pcf', '0005_pedidoreembolso_area_and_more'),
    ]

    operations = [
        migrations.RunPython(puxar_a_area_do_solicitante, nao_da_para_desfazer),
    ]
