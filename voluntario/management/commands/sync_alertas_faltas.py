from django.core.management.base import BaseCommand
from django.utils import timezone

from voluntario.models import Voluntario, Ocorrencia, PresencaVoluntario


class Command(BaseCommand):
    help = "Gera alertas AL2 retroativos para voluntarios com 3+ faltas sem alerta correspondente."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Apenas lista o que seria criado, sem salvar.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        criados = 0

        voluntarios = Voluntario.objects.filter(is_active=True)
        for v in voluntarios:
            total_faltas = PresencaVoluntario.objects.filter(voluntario=v, presenca='AUSENTE').count()
            if total_faltas < 3:
                continue

            alertas_esperados = total_faltas // 3
            alertas_existentes = Ocorrencia.objects.filter(
                advertido=v, tipo='ALERTA', regra='AL2', deleted_at__isnull=True
            ).count()
            faltam = alertas_esperados - alertas_existentes

            if faltam <= 0:
                continue

            nome = v.get_full_name() or v.username
            self.stdout.write(f"  {nome}: {total_faltas} faltas → {faltam} alerta(s) AL2 a criar")

            if not dry:
                for _ in range(faltam):
                    Ocorrencia.objects.create(
                        advertido=v,
                        tipo='ALERTA',
                        regra='AL2',
                        razao=f'Alerta retroativo: {total_faltas} faltas acumuladas (sync_alertas_faltas).',
                        aplicado_por=None,
                        automatico=True,
                    )
                    criados += 1

                # Verifica se novos alertas geram advertencia automatica
                total_alt = Ocorrencia.objects.filter(
                    advertido=v, tipo='ALERTA', deleted_at__isnull=True
                ).count()
                adv_auto_esperadas = total_alt // 3
                adv_auto_existentes = Ocorrencia.objects.filter(
                    advertido=v, tipo='ADVERTENCIA', automatico=True, deleted_at__isnull=True
                ).count()
                for _ in range(adv_auto_esperadas - adv_auto_existentes):
                    Ocorrencia.objects.create(
                        advertido=v,
                        tipo='ADVERTENCIA',
                        razao='Advertencia automatica retroativa por acumulo de 3 alertas (sync_alertas_faltas).',
                        aplicado_por=None,
                        automatico=True,
                    )
                    self.stdout.write(f"    -> Advertencia automatica criada para {nome}")

        if dry:
            self.stdout.write(self.style.WARNING("Dry run — nada foi salvo."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Concluido: {criados} alerta(s) AL2 criados."))
