"""Autoriza o PCF a ler o Google Drive COMO você. Rodar UMA VEZ, na sua máquina.

Alternativa à conta de serviço, para o caso em que quem configura consegue LER
a pasta mas não consegue COMPARTILHÁ-LA com outra identidade — pasta da
organização, sem direito de compartilhamento. O OAuth não precisa que ninguém
compartilhe nada: o PCF passa a enxergar exatamente o que a sua conta enxerga.

    python manage.py autorizar_acervo_drive caminho/do/client_secret.json

Roda na SUA máquina, não no servidor: abre o navegador para você aprovar. No
fim imprime três linhas para colar no .env do PythonAnywhere.

O refresh token impresso é SEGREDO, do mesmo peso de uma senha. Não cole em
chat, não suba para o repositório.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from acervo.drive import ESCOPOS


class Command(BaseCommand):
    help = ('Autoriza o acesso ao Google Drive com a SUA conta. '
            'Rode uma vez, na sua máquina, e cole a saída no .env do servidor.')

    def add_arguments(self, parser):
        parser.add_argument(
            'client_secret',
            help='JSON do OAuth client (tipo "App para computador"), baixado '
                 'do Google Cloud Console.')
        parser.add_argument(
            '--porta', type=int, default=8765,
            help='Porta do servidor local que recebe a resposta do Google.')

    def handle(self, *args, **opcoes):
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            raise CommandError(
                'Falta a biblioteca do fluxo OAuth. Rode:\n'
                '  pip install google-auth-oauthlib')

        # expanduser: nem o Python nem o PowerShell expandem "~" num argumento
        # que vai direto para o programa, e o erro que sai (FileNotFoundError
        # com o "~" literal no caminho) não sugere a causa.
        caminho = Path(opcoes['client_secret']).expanduser()
        if not caminho.is_file():
            raise CommandError(
                f'Não achei o arquivo: {caminho}\n\n'
                'É o JSON do OAuth client baixado do Google Cloud Console — o '
                'nome costuma começar com "client_secret_". Passe o caminho '
                'completo se o atalho "~" não funcionar no seu terminal.')

        fluxo = InstalledAppFlow.from_client_secrets_file(
            str(caminho), scopes=ESCOPOS)

        self.stdout.write(
            'Vai abrir o navegador. Entre com a conta que enxerga a pasta do '
            'acervo no Drive.\n')

        # access_type=offline e prompt=consent juntos: sem os dois, uma segunda
        # autorização da mesma conta devolve só o access token (1 hora) e NENHUM
        # refresh token — e a sincronização morreria em uma hora sem explicação.
        credenciais = fluxo.run_local_server(
            port=opcoes['porta'],
            access_type='offline',
            prompt='consent',
        )

        if not credenciais.refresh_token:
            raise CommandError(
                'O Google não devolveu refresh token. Isso acontece quando a '
                'conta já autorizou este app antes. Remova o acesso em '
                'myaccount.google.com/permissions e rode de novo.')

        self.stdout.write(self.style.SUCCESS(
            '\nAutorizado. Cole estas três linhas no .env do servidor:\n'))
        self.stdout.write(f'ACERVO_DRIVE_OAUTH_CLIENT_ID={credenciais.client_id}')
        self.stdout.write(f'ACERVO_DRIVE_OAUTH_CLIENT_SECRET={credenciais.client_secret}')
        self.stdout.write(f'ACERVO_DRIVE_OAUTH_REFRESH_TOKEN={credenciais.refresh_token}')
        self.stdout.write(self.style.WARNING(
            '\nO refresh token acima é SEGREDO, do mesmo peso de uma senha. '
            'Não cole em chat nem suba para o repositório.\n'
            'Se o .env já tiver ACERVO_DRIVE_CREDENCIAIS (conta de serviço), '
            'apague essa linha — ela tem precedência sobre estas.'))
