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
from django.db import connection, transaction
from django.utils import timezone

from . import drive
from .importacao import (ano_em, motivo_para_recusar,
                        nome_e_ordem_da_pasta, titulo_de)
from .models import Colecao, Documento, SincronizacaoDrive

logger = logging.getLogger('acervo')

# Preenche o "de quem é" dos documentos que vêm do Drive. O modelo exige dizer
# de quem é (Documento.clean), e numa sincronização automática não há como
# saber. Atribuir ao projeto é honesto: o documento é do acervo institucional.
# Quem souber a pessoa corrige na tela depois.
DONO_PADRAO = 'Projeto Criança Feliz'


# Quantos motivos diferentes cabem no relatório. O acervo real gerou mais de 60
# motivos distintos, a maioria com uma ocorrência só — a lista virou várias
# telas e foi cortada no meio de uma palavra ao ser gravada no registro.
MOTIVOS_NO_RELATORIO = 12


class Placar:
    """Contagem de uma rodada, e o texto que a tela vai mostrar."""

    def __init__(self):
        self.trazidos = 0
        self.bytes = 0
        # Arquivo nativo do Google (Docs, Planilhas) não informa tamanho pela
        # API: só se sabe depois de exportar. Contá-los à parte é o que impede
        # o total em MB de parecer exato quando não é.
        self.sem_tamanho = 0
        self.motivos = {}
        self.por_colecao = []

    def pular(self, motivo):
        self.motivos[motivo] = self.motivos.get(motivo, 0) + 1

    def contar(self, tamanho):
        self.trazidos += 1
        if tamanho is None:
            self.sem_tamanho += 1
        else:
            self.bytes += tamanho

    @property
    def pulados(self):
        return sum(self.motivos.values())

    @property
    def megabytes(self):
        return self.bytes / (1024 * 1024)

    def fechar_colecao(self, nome, quantos, bytes_da_colecao=0):
        if quantos:
            mb = bytes_da_colecao / (1024 * 1024)
            self.por_colecao.append(f'{nome}: {quantos} novo(s), {mb:.1f} MB')

    def texto(self):
        linhas = list(self.por_colecao) or ['Nada novo no Drive.']

        if self.trazidos:
            # O total em MB é o número que decide se cabe no disco do servidor.
            # Sem ele, "12807 documentos" não diz nada sobre o risco — e disco
            # cheio no PythonAnywhere derruba o site inteiro, não só a
            # importação.
            linhas.append('')
            linhas.append(
                f'TOTAL: {self.trazidos} documento(s), {self.megabytes:.1f} MB')
            if self.sem_tamanho:
                linhas.append(
                    f'  (+{self.sem_tamanho} arquivo(s) do Google sem tamanho '
                    f'informado — o total acima está subestimado)')

        if self.motivos:
            linhas.append('')
            linhas.append(f'PULADOS: {self.pulados}')
            # Motivos agregados: "12x formato .mp4 não aceito" em vez de doze
            # linhas iguais. É o que responde "por que meu arquivo não apareceu?".
            ordenados = sorted(self.motivos.items(), key=lambda i: -i[1])
            for motivo, quantos in ordenados[:MOTIVOS_NO_RELATORIO]:
                linhas.append(f'  {quantos}x {motivo}')
            resto = ordenados[MOTIVOS_NO_RELATORIO:]
            if resto:
                linhas.append(f'  e mais {sum(q for _, q in resto)} arquivo(s) '
                              f'em {len(resto)} outros motivos')

        return '\n'.join(linhas)


def _soltar_a_conexao():
    """Fecha a conexão com o banco antes de uma espera longa na rede.

    Uma rodada varre 15 árvores no Drive e leva vários minutos. A conexão com o
    MySQL, aberta no início e PARADA esse tempo todo, é derrubada pelo servidor
    por inatividade (erro 4031 no PythonAnywhere) — e a próxima consulta estoura
    sem nada a ver com o Drive.

    Fechar não custa nada: o Django abre uma nova, sozinho, na próxima consulta.
    Segurar uma conexão ociosa durante uma espera de rede é que é o erro.
    """
    try:
        connection.close()
    except Exception:
        # Fechar conexão já morta pode levantar; não é motivo para abortar.
        logger.debug('Falha ao fechar a conexão com o banco', exc_info=True)


def ids_ja_no_acervo():
    """Todos os IDs do Drive já importados, numa consulta só.

    Antes era uma consulta POR ARQUIVO. Num acervo de milhares de arquivos isso
    é milhares de idas ao banco intercaladas com chamadas ao Drive — lento, e
    cada intervalo entre elas é uma chance a mais de a conexão morrer.
    """
    return set(
        Documento.objects
        .exclude(origem_drive_id=None)
        .values_list('origem_drive_id', flat=True)
    )


def _colecao_para(nome, ordem, criar):
    colecao = Colecao.objects.filter(nome=nome).first()
    if colecao or not criar:
        return colecao
    return Colecao.objects.create(
        nome=nome, ordem=ordem, descricao='Sincronizado do Google Drive.')


def _trazer(servico, arquivo, colecao, ano, dono):
    """Baixa e grava um documento. Devolve o Documento criado."""
    nome = drive.nome_para_salvar(arquivo)

    # Baixar é rede: pode demorar num arquivo grande. Solta a conexão antes,
    # para não voltar do download com um cursor que o MySQL já derrubou.
    _soltar_a_conexao()
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
                dono=DONO_PADRAO, somente=None):
    """Percorre o Drive e traz o que falta. Devolve o Placar.

    Cada subpasta do primeiro nível vira uma coleção, igual ao comando de pasta
    local — a estrutura que a liderança já mantém no Drive é a estrutura do
    acervo, e inventar outra só criaria duas verdades.

    `somente` limita a essas pastas (nomes, com ou sem o prefixo de ordenação).
    Serve para trazer pasta por pasta em vez de tudo de uma vez, que é como se
    decide o que entra num acervo aberto a todo voluntário.
    """
    placar = placar or Placar()
    filtro = {p.strip().lower() for p in (somente or [])}

    # Uma consulta só, antes de qualquer espera de rede.
    ja_importados = ids_ja_no_acervo()

    for pasta in drive.subpastas(servico, pasta_raiz_id):
        bruto = (pasta.get('name') or '').strip()
        nome_colecao, ordem = nome_e_ordem_da_pasta(bruto)
        if not nome_colecao:
            continue
        if filtro and not {bruto.lower(), nome_colecao.lower()} & filtro:
            continue

        # A varredura desta pasta pode levar minutos. Nada de segurar uma
        # conexão com o banco parada durante ela.
        _soltar_a_conexao()
        arquivos = drive.arquivos_da_arvore(servico, pasta['id'], nome_colecao)

        novos = 0
        bytes_da_colecao = 0
        colecao = None

        for arquivo in arquivos:
            if arquivo['id'] in ja_importados:
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
                bytes_da_colecao += tamanho or 0
                placar.contar(tamanho)
                continue

            # A coleção só nasce quando o primeiro documento dela vai entrar.
            # Assim uma pasta cujos arquivos foram todos recusados não deixa
            # coleção vazia na tela do acervo.
            if colecao is None:
                colecao = _colecao_para(nome_colecao, ordem, criar=True)

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

            ja_importados.add(arquivo['id'])
            novos += 1
            bytes_da_colecao += tamanho or 0
            placar.contar(tamanho)

        placar.fechar_colecao(nome_colecao, novos, bytes_da_colecao)

    return placar


def rodar(disparada_por=None, dry_run=False, somente=None):
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
                             dry_run=dry_run, somente=somente)
    except Exception as erro:
        logger.exception('Sincronização do acervo falhou')
        # A falha mais provável numa rodada longa é a própria conexão com o
        # banco ter morrido de inatividade — e aí gravar o registro do erro na
        # MESMA conexão morta estoura de novo, e a falha não fica registrada em
        # lugar nenhum. Foi exatamente o que aconteceu na primeira rodada real.
        _soltar_a_conexao()
        try:
            registro.status = SincronizacaoDrive.ERRO
            registro.detalhe = str(erro)[:2000]
            registro.terminou_em = timezone.now()
            registro.save()
        except Exception:
            logger.exception('Não consegui nem registrar a falha da sincronização')
        return registro

    _soltar_a_conexao()
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
