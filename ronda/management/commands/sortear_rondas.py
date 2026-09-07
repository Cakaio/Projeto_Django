# ronda/management/commands/sortear_rondas.py
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Executa o sorteio de rondas para o próximo sábado (rodar toda sexta às 17h)'

    def handle(self, *args, **options):
        from ronda.models import ConfiguracaoRondaSabado
        from ronda.sorteio import executar_sorteio

        hoje = timezone.localdate()
        if hoje.weekday() != 4:  # 4 = sexta-feira
            self.stdout.write(self.style.WARNING(
                f'Hoje é {hoje.strftime("%A")} — este comando só executa às sextas. Nenhuma ação.'
            ))
            return

        cfg = (
            ConfiguracaoRondaSabado.objects
            .filter(status='PENDENTE_SORTEIO', sabado__data__gt=hoje)
            .order_by('sabado__data')
            .first()
        )

        if cfg is None:
            self.stdout.write(self.style.WARNING(
                'Nenhuma configuração pendente de sorteio para o próximo sábado.'
            ))
            return

        if not cfg.horarios.exists():
            self.stdout.write(self.style.ERROR(
                f'Configuração {cfg} não tem horários — sorteio cancelado.'
            ))
            return

        executar_sorteio(cfg)
        self.stdout.write(self.style.SUCCESS(
            f'Sorteio executado para {cfg.sabado.data} com sucesso.'
        ))
