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
        parser.add_argument(
            '--verificar', action='store_true',
            help='Só testa a conexão: diz o que a conta de serviço enxerga na '
                 'pasta. Use logo depois de configurar.')

    def handle(self, *args, **opcoes):
        if not drive.configurado():
            raise CommandError(
                f'Sincronização não configurada: {drive.motivo_de_estar_desligado()}')

        if opcoes['verificar']:
            return self._verificar()

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

    def _verificar(self):
        """Diagnóstico da configuração: o que a conta de serviço enxerga?

        Existe porque o modo de falha mais comum aqui é MUDO: pasta não
        compartilhada com a conta de serviço, ou pasta dentro de um Drive
        compartilhado, devolvem lista VAZIA sem levantar erro nenhum. Sem este
        comando, o sintoma seria "sincronizou e não trouxe nada" — que é
        indistinguível de "não há nada novo".
        """
        from django.conf import settings

        self.stdout.write(f'Pasta configurada: {settings.ACERVO_DRIVE_PASTA_ID}')
        self.stdout.write(f'Credencial: {settings.ACERVO_DRIVE_CREDENCIAIS}')

        try:
            servico = drive.cliente()
        except Exception as erro:
            raise CommandError(
                f'Não consegui autenticar: {erro}\n\n'
                'Confira se o caminho do JSON existe e se a Google Drive API '
                'está ATIVADA no projeto do Google Cloud.')

        try:
            pastas = drive.subpastas(servico, settings.ACERVO_DRIVE_PASTA_ID)
        except Exception as erro:
            raise CommandError(
                f'Autenticou, mas não consegui ler a pasta: {erro}\n\n'
                'O erro 404 aqui quase sempre significa que a pasta NÃO foi '
                'compartilhada com o e-mail da conta de serviço.')

        if not pastas:
            self.stdout.write(self.style.ERROR(
                '\nA conta de serviço não enxerga NENHUMA subpasta.\n\n'
                'Três causas, em ordem de probabilidade:\n'
                '  1. A pasta não foi compartilhada com o e-mail da conta de '
                'serviço (o que termina em .iam.gserviceaccount.com).\n'
                '  2. O ID da pasta está errado — é o trecho depois de '
                '/folders/ na URL, sem o ?usp=... do final.\n'
                '  3. A pasta existe mas não tem subpastas: cada subpasta do '
                'primeiro nível é que vira uma coleção. Arquivo solto na raiz '
                'não é importado.'))
            return

        self.stdout.write(self.style.SUCCESS(
            f'\nConexão OK. {len(pastas)} subpasta(s) visíveis:\n'))
        total = 0
        for pasta in pastas:
            arquivos = drive.arquivos_da_arvore(servico, pasta['id'], pasta['name'])
            total += len(arquivos)
            self.stdout.write(f"  {pasta['name']} — {len(arquivos)} arquivo(s)")

        self.stdout.write(self.style.SUCCESS(
            f'\n{total} arquivo(s) no total. Rode --dry-run para ver quantos '
            f'entrariam de fato no acervo.'))
