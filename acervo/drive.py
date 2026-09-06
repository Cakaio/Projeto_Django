"""Conversa com o Google Drive. Só isto — nada de regra do Acervo aqui.

A separação é o que torna a sincronização testável: `acervo/sincronizacao.py`
recebe um cliente como argumento e não sabe se ele fala com o Google ou é um
dublê de teste. Sem isso, testar a importação exigiria rede e credencial de
verdade.

Autenticação por CONTA DE SERVIÇO, e não OAuth de usuário. Motivo concreto: em
app não verificado pelo Google, o refresh token do OAuth expira em 7 dias — a
sincronização pararia sozinha toda semana e ninguém entenderia por quê. A conta
de serviço não expira; basta compartilhar a pasta do Drive com o e-mail dela
como Leitor.

Import protegido pelo mesmo motivo do pywebpush em notificacoes/services.py:
este módulo é alcançado pelo URLconf, e um ImportError aqui derrubaria o site
inteiro se a dependência não estivesse instalada no servidor.
"""
import io
import logging

from django.conf import settings

try:
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload
except ImportError:  # pragma: no cover - ambiente sem a dependência
    service_account = None
    Credentials = None
    build = None
    MediaIoBaseDownload = None

    class HttpError(Exception):
        """Substituto para quando o google-api-python-client não está instalado."""

logger = logging.getLogger('acervo')

# Só leitura. A conta de serviço nunca precisa escrever no Drive, e pedir escopo
# a mais é dar poder que ninguém vai usar.
ESCOPOS = ['https://www.googleapis.com/auth/drive.readonly']

TIPO_PASTA = 'application/vnd.google-apps.folder'

# Arquivos nativos do Google não são arquivos: não têm bytes para baixar, só
# podem ser EXPORTADOS. O Acervo aceita PDF, então é para PDF que exportamos.
EXPORTAVEIS = {
    'application/vnd.google-apps.document': 'application/pdf',
    'application/vnd.google-apps.presentation': 'application/pdf',
    'application/vnd.google-apps.spreadsheet': 'application/pdf',
    'application/vnd.google-apps.drawing': 'application/pdf',
}

# Campos pedidos na listagem. Pedir só o necessário deixa a resposta menor e a
# paginação mais rápida.
CAMPOS = 'nextPageToken, files(id, name, mimeType, size, modifiedTime)'


class DriveIndisponivel(Exception):
    """A configuração está incompleta ou o Google recusou o acesso."""


def _tem_conta_de_servico() -> bool:
    return bool(getattr(settings, 'ACERVO_DRIVE_CREDENCIAIS', ''))


def _tem_oauth() -> bool:
    return all(getattr(settings, nome, '') for nome in (
        'ACERVO_DRIVE_OAUTH_CLIENT_ID',
        'ACERVO_DRIVE_OAUTH_CLIENT_SECRET',
        'ACERVO_DRIVE_OAUTH_REFRESH_TOKEN',
    ))


def configurado() -> bool:
    """Dá para falar com o Drive?

    Dois modos de autenticação, e a escolha entre eles não é de gosto:

    CONTA DE SERVIÇO — o PCF é uma identidade própria. Exige que alguém
    COMPARTILHE a pasta com ela, e portanto exige ter direito de compartilhar.

    OAUTH DO USUÁRIO — o PCF lê o Drive COMO uma pessoa, com a permissão que
    ela já tem. É a saída para quem consegue ler a pasta mas não consegue
    conceder acesso a outra identidade — o caso deste projeto, onde a pasta é da
    organização e nem todo mundo pode compartilhá-la.
    """
    return bool(
        build is not None
        and getattr(settings, 'ACERVO_DRIVE_PASTA_ID', '')
        and (_tem_conta_de_servico() or _tem_oauth())
    )


def modo_de_autenticacao() -> str:
    if _tem_conta_de_servico():
        return 'conta de serviço'
    if _tem_oauth():
        return 'OAuth de usuário'
    return ''


def motivo_de_estar_desligado() -> str:
    """Frase única para log e para tela — o que exatamente falta."""
    if build is None:
        return ('google-api-python-client não instalado — rode '
                'pip install -r requirements.txt no virtualenv do site')

    if not getattr(settings, 'ACERVO_DRIVE_PASTA_ID', ''):
        return 'faltando no .env: ACERVO_DRIVE_PASTA_ID'

    if not (_tem_conta_de_servico() or _tem_oauth()):
        return ('faltando credencial no .env: ou ACERVO_DRIVE_CREDENCIAIS '
                '(conta de serviço), ou as três ACERVO_DRIVE_OAUTH_* '
                '(rode: python manage.py autorizar_acervo_drive)')
    return ''


def _credenciais():
    """Credencial do modo configurado. Conta de serviço tem precedência."""
    if _tem_conta_de_servico():
        return service_account.Credentials.from_service_account_file(
            settings.ACERVO_DRIVE_CREDENCIAIS, scopes=ESCOPOS)

    # Só o refresh token é guardado. O access token, que dura uma hora, é
    # obtido na hora pela própria biblioteca — guardar um token de uma hora no
    # .env seria inútil.
    return Credentials(
        token=None,
        refresh_token=settings.ACERVO_DRIVE_OAUTH_REFRESH_TOKEN,
        client_id=settings.ACERVO_DRIVE_OAUTH_CLIENT_ID,
        client_secret=settings.ACERVO_DRIVE_OAUTH_CLIENT_SECRET,
        token_uri='https://oauth2.googleapis.com/token',
        scopes=ESCOPOS,
    )


def cliente():
    """Serviço do Drive autenticado.

    Levanta DriveIndisponivel quando falta configuração — quem chama transforma
    isso em mensagem na tela, em vez de num traceback.
    """
    if not configurado():
        raise DriveIndisponivel(motivo_de_estar_desligado())

    # cache_discovery=False: o cache em disco do discovery quebra em ambiente
    # sem permissão de escrita e polui o log com avisos.
    return build('drive', 'v3', credentials=_credenciais(), cache_discovery=False)


def _listar(servico, consulta):
    """Todos os itens de uma consulta, seguindo a paginação até o fim.

    `supportsAllDrives` e `includeItemsFromAllDrives`: sem os dois, uma pasta
    que vive num Drive compartilhado (não no "Meu Drive" de alguém) volta vazia,
    sem erro nenhum — é o modo de falha mais confuso da API.
    """
    itens, pagina = [], None
    while True:
        resposta = servico.files().list(
            q=consulta,
            fields=CAMPOS,
            pageToken=pagina,
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        itens.extend(resposta.get('files', []))
        pagina = resposta.get('nextPageToken')
        if not pagina:
            return itens


def metadados(servico, arquivo_id):
    """Dados da própria pasta/arquivo — nome, dono, e se está num Drive compartilhado.

    Serve ao diagnóstico. `files.list` com um pai que a conta de serviço não
    enxerga devolve lista VAZIA em vez de erro, então listar não distingue "não
    tenho acesso" de "a pasta está vazia". Já `files.get` no próprio ID levanta
    404 quando não há acesso — é a pergunta que separa os dois casos.
    """
    return servico.files().get(
        fileId=arquivo_id,
        fields='id, name, mimeType, driveId, owners(emailAddress)',
        supportsAllDrives=True,
    ).execute()


def subpastas(servico, pasta_id):
    """Pastas filhas diretas. Cada uma vira uma coleção do Acervo."""
    return _listar(
        servico,
        f"'{pasta_id}' in parents and mimeType = '{TIPO_PASTA}' and trashed = false")


def arquivos_da_arvore(servico, pasta_id, nome_da_pasta=''):
    """Arquivos abaixo desta pasta, em qualquer profundidade.

    A API não sabe buscar recursivamente: `'X' in parents` só devolve os filhos
    diretos. Então descemos nível a nível.

    Cada arquivo volta com a chave extra `pastas`: os nomes das pastas acima
    dele, da mais interna para a mais externa. É disso que sai o ano quando o
    nome do arquivo não tem — em "Postulações/2023/joao.pdf", o ano está na
    pasta do meio, que uma varredura plana perderia.
    """
    encontrados = []
    fila = [(pasta_id, [nome_da_pasta] if nome_da_pasta else [])]
    vistas = {pasta_id}
    while fila:
        atual, caminho = fila.pop()
        for item in _listar(servico, f"'{atual}' in parents and trashed = false"):
            if item['mimeType'] == TIPO_PASTA:
                # `vistas` protege contra atalho que aponta para uma pasta já
                # visitada — sem isso, o laço não termina.
                if item['id'] not in vistas:
                    vistas.add(item['id'])
                    fila.append((item['id'], [item['name']] + caminho))
            else:
                encontrados.append({**item, 'pastas': caminho})
    return encontrados


def nome_para_salvar(arquivo):
    """Nome de arquivo com extensão, já considerando a exportação para PDF."""
    nome = arquivo.get('name', 'sem-nome')
    if arquivo.get('mimeType') in EXPORTAVEIS:
        return f"{nome}.pdf" if not nome.lower().endswith('.pdf') else nome
    return nome


def baixar(servico, arquivo) -> bytes:
    """Bytes do arquivo. Exporta para PDF se for nativo do Google."""
    tipo = arquivo.get('mimeType')
    if tipo in EXPORTAVEIS:
        pedido = servico.files().export_media(
            fileId=arquivo['id'], mimeType=EXPORTAVEIS[tipo])
    else:
        pedido = servico.files().get_media(
            fileId=arquivo['id'], supportsAllDrives=True)

    buffer = io.BytesIO()
    baixador = MediaIoBaseDownload(buffer, pedido)
    terminou = False
    while not terminou:
        _, terminou = baixador.next_chunk()
    return buffer.getvalue()
