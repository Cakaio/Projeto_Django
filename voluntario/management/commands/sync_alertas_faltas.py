"""Varredura retroativa dos alertas de falta.

Este comando já teve régua própria: somava TODAS as faltas do voluntário e
gerava um alerta a cada 3, com a regra AL2 ("confirmou presença e não
compareceu"). Quem faltou 3 sábados espalhados no ano levava alerta, e o texto
da ocorrência não tinha relação com o motivo. Agora ele não decide mais nada:
chama a mesma função do registro de presença, então existe uma régua só — 3
faltas CONSECUTIVAS — e uma regra só.
"""
from django.core.management.base import BaseCommand

from voluntario.models import Voluntario, FALTAS_POR_ALERTA
from voluntario.views import contar_faltas_consecutivas, verificar_faltas_e_gerar_alertas
from sabado.models import Sabado


class Command(BaseCommand):
    help = ("Gera os alertas de falta que ficaram para trás, usando a mesma regra do "
            f"registro de presença: {FALTAS_POR_ALERTA} faltas consecutivas.")

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Apenas lista quem seria alertado, sem salvar.')

    def handle(self, *args, **options):
        dry = options['dry_run']

        ultimo_sabado = Sabado.objects.order_by('-data').first()
        if ultimo_sabado is None:
            self.stdout.write(self.style.WARNING("Nenhum sábado cadastrado — nada a varrer."))
            return

        alertados = 0
        # `ativos()` e não `is_active`: quem saiu do projeto não recebe alerta.
        for v in Voluntario.objects.ativos():
            consecutivas, _ = contar_faltas_consecutivas(v, ultimo_sabado)
            if consecutivas < FALTAS_POR_ALERTA:
                continue

            nome = v.get_full_name() or v.username
            self.stdout.write(f"  {nome}: {consecutivas} faltas consecutivas")
            alertados += 1

            if not dry:
                # Sem e-mail: falta antiga não vira notificação em massa hoje.
                verificar_faltas_e_gerar_alertas(v, ultimo_sabado, None, notificar=False)

        if dry:
            self.stdout.write(self.style.WARNING(f"Dry run — {alertados} voluntário(s) seriam avaliados, nada foi salvo."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Concluído: {alertados} voluntário(s) avaliados."))
