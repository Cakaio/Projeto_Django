"""Traz do Google Drive o que ainda não está no Acervo.

Incremental por construção: cada documento guarda o ID do arquivo no Drive
(`Documento.origem_drive_id`), e o que já tem ID cadastrado é ignorado. Rodar
dez vezes seguidas traz zero documentos na segunda em diante — e renomear ou
mover o arquivo no Drive não faz ele voltar, porque o ID não muda.

Recebe o cliente do Drive como argumento em vez de criá-lo: é o que permite
testar a sincronização inteira com um dublê, sem rede nem credencial. As regras
de "este arquivo entra?" são as mesmas do comando de pasta local
(`acervo/importacao.py`) — não há um caminho para o botão e outro para o
comando.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from . import drive
from .importacao import ano_em, motivo_para_recusar, titulo_de
from .models import Colecao, Documento, SincronizacaoDrive

logger = logging.getLogger('acervo')

# Preenche o "de quem é" dos documentos que vêm do Drive. O modelo exige dizer
# de quem é (Documento.clean), e numa sincronização automática não há como
# saber. Atribuir ao projeto é honesto: o documento é do acervo institucional.
# Quem souber a pessoa corrige na tela depois.
DONO_PADRAO = 'Projeto Criança Feliz'


class Placar:
    """Contagem de uma rodada, e o texto que a tela vai mostrar."""

    def __init__(self):
        self.trazidos = 0
        self.motivos = {}
        self.por_colecao = []

    def pular(self, motivo):
        self.motivos[motivo] = self.motivos.get(motivo, 0) + 1

    @property
    def pulados(self):
        return sum(self.motivos.values())

    def fechar_colecao(self, nome, quantos):
        if quantos:
            self.por_colecao.append(f'{nome}: {quantos} novo(s)')

    def texto(self):
        linhas = list(self.por_colecao) or ['Nada novo no Drive.']
        # Motivos agregados: "12x formato .mp4 não aceito" em vez de doze
        # linhas iguais. É o que responde "por que meu arquivo não apareceu?".
        for motivo, quantos in sorted(self.motivos.items(), key=lambda i: -i[1]):
            linhas.append(f'{quantos}x {motivo}')
        return '\n'.join(linhas)


def _ja_esta_no_acervo(drive_id):
    return Documento.objects.filter(origem_drive_id=drive_id).exists()


def _colecao_para(nome, criar):
    colecao = Colecao.objects.filter(nome=nome).first()
    if colecao or not criar:
        return colecao
    return Colecao.objects.create(
        nome=nome, descricao='Sincronizado do Google Drive.')


def _trazer(servico, arquivo, colecao, ano, dono):
    """Baixa e grava um documento. Devolve o Documento criado."""
    nome = drive.nome_para_salvar(arquivo)
    conteudo = drive.baixar(servico, arquivo)

    with transaction.atomic():
        documento = Documento(
            colecao=colecao,
            titulo=titulo_de(nome),
            ano=ano,
            nome_avulso=dono,
            origem_drive_id=arquivo['id'],
            descricao='Sincronizado do Google Drive.',
        )
        documento.arquivo.save(nome, ContentFile(conteudo), save=False)
        documento.save()
    return documento


def sincronizar(servico, pasta_raiz_id, placar=None, dry_run=False,
                dono=DONO_PADRAO):
    """Percorre o Drive e traz o que falta. Devolve o Placar.

    Cada subpasta do primeiro nível vira uma coleção, igual ao comando de pasta
    local — a estrutura que a liderança já mantém no Drive é a estrutura do
    acervo, e inventar outra só criaria duas verdades.
    """
    placar = placar or Placar()

    for pasta in drive.subpastas(servico, pasta_raiz_id):
        nome_colecao = (pasta.get('name') or '').strip()[:80]
        if not nome_colecao:
            continue

        arquivos = drive.arquivos_da_arvore(servico, pasta['id'], nome_colecao)
        novos = 0
        colecao = None

        for arquivo in arquivos:
            if _ja_esta_no_acervo(arquivo['id']):
                # Não é motivo de aviso: é o caso NORMAL a partir da segunda
                # rodada, e listá-lo encheria o relatório de ruído.
                continue

            nome = drive.nome_para_salvar(arquivo)
            # Arquivo nativo do Google não tem `size` — vai ser exportado, e o
            # tamanho só se conhece depois. None desliga a checagem de tamanho.
            tamanho = int(arquivo['size']) if arquivo.get('size') else None

            recusa = motivo_para_recusar(nome, tamanho)
            if recusa:
                placar.pular(recusa)
                continue

            ano = ano_em([nome] + arquivo.get('pastas', []))
            if ano is None:
                placar.pular('sem ano no nome do arquivo nem da pasta')
                continue

            if dry_run:
                novos += 1
                placar.trazidos += 1
                continue

            # A coleção só nasce quando o primeiro documento dela vai entrar.
            # Assim uma pasta cujos arquivos foram todos recusados não deixa
            # coleção vazia na tela do acervo.
            if colecao is None:
                colecao = _colecao_para(nome_colecao, criar=True)

            try:
                _trazer(servico, arquivo, colecao, ano, dono)
            except drive.HttpError as erro:
                # Um arquivo sem permissão, ou removido entre a listagem e o
                # download, não pode derrubar a sincronização inteira.
                logger.warning('Drive recusou %s: %s', arquivo.get('name'), erro)
                placar.pular('o Drive recusou o download')
                continue
            except Exception:
                logger.exception('Falha ao trazer %s do Drive', arquivo.get('name'))
                placar.pular('falha ao gravar')
                continue

            novos += 1
            placar.trazidos += 1

        placar.fechar_colecao(nome_colecao, novos)

    return placar


def rodar(disparada_por=None, dry_run=False):
    """Uma rodada completa, com registro no banco do começo ao fim.

    O registro existe porque a sincronização roda em thread (o botão não pode
    segurar a resposta) e porque, quando alguém disser "meu arquivo não
    apareceu", a resposta precisa estar no sistema — não no log do servidor,
    que ninguém da liderança alcança.
    """
    registro = SincronizacaoDrive.objects.create(disparada_por=disparada_por)
    try:
        servico = drive.cliente()
        placar = sincronizar(servico, settings.ACERVO_DRIVE_PASTA_ID,
                             dry_run=dry_run)
    except Exception as erro:
        registro.status = SincronizacaoDrive.ERRO
        registro.detalhe = str(erro)[:2000]
        registro.terminou_em = timezone.now()
        registro.save()
        logger.exception('Sincronização do acervo falhou')
        return registro

    registro.status = SincronizacaoDrive.OK
    registro.trazidos = placar.trazidos
    registro.pulados = placar.pulados
    registro.detalhe = placar.texto()[:2000]
    registro.terminou_em = timezone.now()
    registro.save()
    return registro


# Depois disso, um registro ainda marcado como RODANDO é considerado abandonado.
# A sincronização roda em thread daemon: se o servidor for reiniciado no meio
# (deploy, reload do PythonAnywhere), a thread morre sem nunca fechar o
# registro. Sem esta janela, esse registro órfão travaria o botão para sempre.
LIMITE_DE_RODADA = timedelta(hours=2)


def esta_rodando():
    """Já há uma sincronização em andamento?

    Impede o botão de disparar cinco rodadas concorrentes baixando os mesmos
    arquivos — cada uma criaria o mesmo documento, e só o `unique` do
    origem_drive_id evitaria a duplicata, à custa de tráfego jogado fora.
    """
    return SincronizacaoDrive.objects.filter(
        status=SincronizacaoDrive.RODANDO,
        comecou_em__gte=timezone.now() - LIMITE_DE_RODADA,
    ).exists()
