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
            help='Só testa a conexão: diz o que a credencial enxerga na pasta. '
                 'Use logo depois de configurar. É rápido.')
        parser.add_argument(
            '--somente', action='append', default=[],
            help='Traz só estas pastas (repita para várias). Aceita o nome com '
                 'ou sem o prefixo de ordenação: "2018" ou "1. 2018".')
        parser.add_argument(
            '--contar', action='store_true',
            help='Com --verificar, conta os arquivos de cada pasta. Percorre a '
                 'árvore inteira no Drive e demora num acervo grande.')

    def handle(self, *args, **opcoes):
        if not drive.configurado():
            raise CommandError(
                f'Sincronização não configurada: {drive.motivo_de_estar_desligado()}')

        if opcoes['verificar']:
            self.contar = opcoes['contar']
            return self._verificar()

        registro = rodar(disparada_por=None, dry_run=opcoes['dry_run'],
                         somente=opcoes['somente'])

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
        self.stdout.write(f'Autenticando por: {drive.modo_de_autenticacao()}')

        if settings.ACERVO_DRIVE_CREDENCIAIS:
            self.stdout.write(f'  conta de serviço: {settings.ACERVO_DRIVE_CREDENCIAIS}')
            if drive._tem_oauth():
                # Erro fácil de cometer e difícil de perceber: colar as linhas
                # do OAuth sem apagar a da conta de serviço. O código continua
                # usando a conta de serviço e o sintoma é "configurei o OAuth e
                # continua dando 404".
                self.stdout.write(self.style.WARNING(
                    '  ATENÇÃO: o OAuth também está configurado, mas a conta de '
                    'serviço tem precedência e é ela que está sendo usada.\n'
                    '  Para usar o OAuth, apague a linha ACERVO_DRIVE_CREDENCIAIS '
                    'do .env.'))
        else:
            self.stdout.write(
                f'  cliente OAuth: {settings.ACERVO_DRIVE_OAUTH_CLIENT_ID[:32]}...')

        try:
            servico = drive.cliente()
        except Exception as erro:
            raise CommandError(
                f'Não consegui autenticar: {erro}\n\n'
                'Confira se o caminho do JSON existe e se a Google Drive API '
                'está ATIVADA no projeto do Google Cloud.')

        # Pergunta pela PRÓPRIA pasta antes de listar o conteúdo. `files.list`
        # com um pai invisível devolve lista vazia sem erro; `files.get` no ID
        # levanta 404. É o que separa "não tenho acesso" de "não tem subpasta".
        try:
            pasta = drive.metadados(servico, settings.ACERVO_DRIVE_PASTA_ID)
        except Exception as erro:
            raise CommandError(
                f'A conta de serviço NÃO enxerga essa pasta.\n\n'
                f'Resposta do Google: {erro}\n\n'
                'O compartilhamento não chegou até ela. Causas, em ordem:\n'
                '  1. A organização do Workspace bloqueia compartilhar para fora\n'
                '     do domínio. Uma conta de serviço termina em\n'
                '     .iam.gserviceaccount.com, que é um domínio EXTERNO — o\n'
                '     Google aceita digitar o e-mail e depois não aplica.\n'
                '     Confira em Compartilhar se a conta aparece na LISTA de\n'
                '     pessoas com acesso. Se não aparecer, foi isso.\n'
                '  2. A pasta está num Drive compartilhado que não aceita\n'
                '     membros externos.\n'
                '  3. O ID da pasta está errado.')

        dono = (pasta.get('owners') or [{}])[0].get('emailAddress', '—')
        self.stdout.write(self.style.SUCCESS(
            f"\nEnxergo a pasta: {pasta.get('name')} (dono: {dono})"))
        if pasta.get('driveId'):
            self.stdout.write(
                'Ela está num Drive compartilhado — o acesso vem da participação '
                'no Drive, não do compartilhamento da pasta.')

        try:
            pastas = drive.subpastas(servico, settings.ACERVO_DRIVE_PASTA_ID)
        except Exception as erro:
            raise CommandError(f'Não consegui listar o conteúdo: {erro}')

        if not pastas:
            self.stdout.write(self.style.ERROR(
                '\nEnxergo a pasta, mas ela não tem NENHUMA subpasta visível.\n\n'
                'Cada subpasta do primeiro nível é que vira uma coleção — '
                'arquivo solto na raiz não é importado. Se você vê subpastas '
                'no navegador e elas não aparecem aqui, o compartilhamento '
                'pode ter sido feito só na pasta de cima, sem herança.'))
            return

        self.stdout.write(self.style.SUCCESS(
            f'\nConexão OK. {len(pastas)} subpasta(s) visíveis — '
            f'cada uma vira uma coleção:\n'))

        for pasta in sorted(pastas, key=lambda p: p.get('name', '')):
            self.stdout.write(f"  {pasta['name']}")

        if not self.contar:
            self.stdout.write(
                '\nPara contar os arquivos de cada uma, rode com --contar. '
                'Isso percorre a árvore inteira no Drive e pode demorar '
                'vários minutos num acervo grande.')
            return

        # A contagem desce a árvore inteira de cada pasta: são muitas chamadas
        # sequenciais à API. Imprime e descarrega a saída pasta a pasta — sem
        # isso, um acervo grande fica minutos mudo e parece travado, que foi
        # exatamente o que aconteceu na primeira versão deste comando.
        self.stdout.write('\nContando (uma linha por pasta, conforme termina):\n')
        total = 0
        for pasta in sorted(pastas, key=lambda p: p.get('name', '')):
            arquivos = drive.arquivos_da_arvore(servico, pasta['id'], pasta['name'])
            total += len(arquivos)
            self.stdout.write(f"  {pasta['name']} — {len(arquivos)} arquivo(s)")
            self.stdout.flush()

        self.stdout.write(self.style.SUCCESS(
            f'\n{total} arquivo(s) no total. Rode --dry-run para ver quantos '
            f'entrariam de fato no acervo.'))
