"""Traz do Google Drive o que ainda não está no Acervo.

Feito para rodar em tarefa agendada no PythonAnywhere, uma vez por dia — é o que
faz "alguém botou algo novo lá" aparecer no Acervo sem ninguém lembrar de
clicar. O mesmo trabalho é disparado pelo botão na tela do acervo.

    python manage.py sincronizar_acervo_drive --dry-run
    python manage.py sincronizar_acervo_drive

Incremental: cada documento guarda o ID do arquivo no Drive, e o que já entrou é
ignorado. Rodar de novo não retraz nada, e renomear o arquivo no Drive também
não faz ele voltar.
"""
from django.core.management.base import BaseCommand, CommandError

from acervo import drive
from acervo.models import SincronizacaoDrive
from acervo.sincronizacao import rodar


class Command(BaseCommand):
    help = ('Sincroniza o Acervo com a pasta do Google Drive. '
            'Só traz o que ainda não entrou.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Conta o que entraria, sem baixar nem gravar nada.')

    def handle(self, *args, **opcoes):
        if not drive.configurado():
            raise CommandError(
                f'Sincronização não configurada: {drive.motivo_de_estar_desligado()}')

        registro = rodar(disparada_por=None, dry_run=opcoes['dry_run'])

        if registro.status == SincronizacaoDrive.ERRO:
            # Sai com código de erro para a tarefa agendada do PythonAnywhere
            # registrar a falha, em vez de reportar sucesso silencioso.
            raise CommandError(f'Sincronização falhou: {registro.detalhe}')

        self.stdout.write(registro.detalhe)
        self.stdout.write(self.style.SUCCESS(
            f'{registro.trazidos} trazido(s), {registro.pulados} pulado(s), '
            f'em {registro.duracao_em_segundos}s.'))
        if opcoes['dry_run']:
            self.stdout.write(self.style.WARNING(
                '--dry-run: nada foi baixado nem gravado.'))
