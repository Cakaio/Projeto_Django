"""Importa uma árvore de pastas para o Acervo.

Feito para a migração do Drive: baixe a pasta do Google Drive (ela vem como
.zip preservando a estrutura), descompacte, e aponte este comando para ela.

    python manage.py importar_acervo /caminho/da/pasta --dry-run
    python manage.py importar_acervo /caminho/da/pasta

Cada SUBPASTA do primeiro nível vira uma Coleção; os arquivos dentro dela (em
qualquer profundidade) viram Documentos dessa coleção.

Por que uma pasta local e não a API do Google: falar direto com o Drive exigiria
projeto no Google Cloud, credencial de serviço, mais uma dependência e mais um
segredo no .env — para uma migração que acontece uma vez. Com pasta local o
mesmo comando serve para qualquer lote futuro, venha do Drive, de um HD ou do
computador de alguém.

SEMPRE rode com --dry-run primeiro. Ele não escreve nada e mostra exatamente o
que entraria, o que ficaria de fora e por quê.
"""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from acervo.forms import TAMANHO_MAXIMO_MB
from acervo.importacao import (ano_em, motivo_para_recusar, titulo_de)
from acervo.models import Colecao, Documento
from voluntario.models import Voluntario


def partes_do_caminho(caminho: Path, raiz: Path):
    """Nomes a consultar em busca do ano, do mais específico para o mais genérico.

    Nome do arquivo primeiro, depois as pastas de dentro para fora — é o que faz
    "ata-2023.pdf" dentro de "Postulações 2019/" ser de 2023.
    """
    partes = [caminho.stem]
    atual = caminho.parent
    while atual != raiz and atual != atual.parent:
        partes.append(atual.name)
        atual = atual.parent
    partes.append(raiz.name)
    return partes


class Command(BaseCommand):
    help = ('Importa uma árvore de pastas para o Acervo. Cada subpasta do '
            'primeiro nível vira uma coleção. Rode com --dry-run antes.')

    def add_arguments(self, parser):
        parser.add_argument('pasta', help='Pasta raiz, já descompactada.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Não escreve nada. Mostra o que entraria e o que ficaria de fora.')
        parser.add_argument(
            '--ano', type=int, default=None,
            help='Ano a usar quando não houver ano no nome do arquivo nem da pasta.')
        parser.add_argument(
            '--nome-padrao', default='',
            help='Preenche o campo "de quem é" nos documentos sem atribuição. '
                 'Sem isso, esses documentos são pulados — o modelo exige dizer '
                 'de quem é (Documento.clean).')
        parser.add_argument(
            '--enviado-por', default='',
            help='Username do voluntário a registrar como quem enviou.')
        parser.add_argument(
            '--somente', action='append', default=[],
            help='Importa só estas subpastas (repita para várias). '
                 'Sem isso, importa todas.')
        parser.add_argument(
            '--resumo', action='store_true',
            help='Uma linha por coleção em vez de uma por arquivo. Use para '
                 'levantar uma pasta grande antes de decidir o que entra.')

    def handle(self, *args, **opcoes):
        raiz = Path(opcoes['pasta']).expanduser().resolve()
        if not raiz.is_dir():
            raise CommandError(f'{raiz} não é uma pasta.')

        seco = opcoes['dry_run']
        enviado_por = self._quem_enviou(opcoes['enviado_por'])
        somente = {s.lower() for s in opcoes['somente']}

        subpastas = sorted(p for p in raiz.iterdir() if p.is_dir())
        if somente:
            subpastas = [p for p in subpastas if p.name.lower() in somente]
        if not subpastas:
            raise CommandError(
                'Nenhuma subpasta encontrada. Cada subpasta do primeiro nível '
                'vira uma coleção — arquivos soltos na raiz não são importados.')

        soltos = [p for p in raiz.iterdir() if p.is_file()]
        if soltos:
            self.stdout.write(self.style.WARNING(
                f'{len(soltos)} arquivo(s) solto(s) na raiz serão ignorados — '
                f'mova-os para uma subpasta se quiser importá-los.'))

        total = {'entram': 0, 'pulados': 0, 'bytes': 0}
        for subpasta in subpastas:
            self._processar_colecao(
                subpasta, raiz, seco, opcoes['ano'], opcoes['nome_padrao'],
                enviado_por, total, opcoes['resumo'])

        self.stdout.write('')
        tamanho = total['bytes'] / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f"TOTAL: {total['entram']} documento(s), {tamanho:.1f} MB. "
            f"{total['pulados']} pulado(s)."))
        if seco:
            self.stdout.write(self.style.WARNING(
                '--dry-run: NADA foi gravado. Confira o disco disponível no '
                'servidor antes de rodar de verdade.'))

    def _quem_enviou(self, username):
        if not username:
            return None
        try:
            return Voluntario.objects.get(username=username)
        except Voluntario.DoesNotExist:
            raise CommandError(f'Voluntário "{username}" não existe.')

    def _processar_colecao(self, subpasta, raiz, seco, ano_padrao, nome_padrao,
                           enviado_por, total, resumo):
        nome = subpasta.name.strip()[:80]
        colecao = Colecao.objects.filter(nome=nome).first()

        self.stdout.write('')
        marca = 'existente' if colecao else 'NOVA'
        self.stdout.write(self.style.MIGRATE_HEADING(f'{nome} ({marca})'))

        criada_agora = False
        if colecao is None and not seco:
            colecao = Colecao.objects.create(
                nome=nome,
                descricao='Importado do acervo digital do projeto.',
            )
            criada_agora = True

        # Contadores desta coleção. No modo resumo é isto que sai; no modo
        # detalhado servem só para a linha de fechamento da coleção.
        placar = {'entram': 0, 'bytes': 0, 'motivos': {}}

        arquivos = sorted(p for p in subpasta.rglob('*') if p.is_file())
        for arquivo in arquivos:
            self._processar_arquivo(
                arquivo, raiz, colecao, seco, ano_padrao, nome_padrao,
                enviado_por, total, placar, resumo)

        # Pasta em que nada entrou não deixa coleção vazia para trás. Acontece
        # de verdade: uma pasta só de vídeo, ou sem ano em lugar nenhum, tem
        # todos os arquivos pulados — e a tela do acervo ficaria com uma coleção
        # que não abre nada. Só apaga a que este comando acabou de criar.
        if criada_agora and placar['entram'] == 0:
            colecao.delete()
            colecao = None

        pulados = sum(placar['motivos'].values())
        self.stdout.write(
            f"  {placar['entram']} documento(s), "
            f"{placar['bytes'] / 1048576:.1f} MB, {pulados} pulado(s)")
        if criada_agora and placar['entram'] == 0:
            self.stdout.write('    (coleção não criada — nada entrou)')
        # Os motivos agregados são o que responde "por que só metade entrou?"
        # sem obrigar a ler mil linhas.
        for motivo, quantos in sorted(placar['motivos'].items(),
                                      key=lambda item: -item[1]):
            self.stdout.write(f'    {quantos}x {motivo}')

    def _processar_arquivo(self, arquivo, raiz, colecao, seco, ano_padrao,
                           nome_padrao, enviado_por, total, placar, resumo):
        relativo = arquivo.relative_to(raiz)

        def pular(motivo, detalhe=''):
            total['pulados'] += 1
            placar['motivos'][motivo] = placar['motivos'].get(motivo, 0) + 1
            if not resumo:
                self.stdout.write(f'  PULADO  {relativo} — {detalhe or motivo}')

        tamanho = arquivo.stat().st_size
        recusa = motivo_para_recusar(arquivo.name, tamanho)
        if recusa:
            detalhe = (f'{tamanho / 1048576:.1f} MB — o limite é {TAMANHO_MAXIMO_MB} MB'
                       if 'acima de' in recusa else '')
            return pular(recusa, detalhe)

        ano = ano_em(partes_do_caminho(arquivo, raiz)) or ano_padrao
        if ano is None:
            return pular('sem ano no nome do arquivo nem da pasta (use --ano)')

        titulo = titulo_de(arquivo.name)

        if colecao is not None and Documento.objects.filter(
                colecao=colecao, titulo=titulo, ano=ano).exists():
            return pular('já está no acervo')

        if not nome_padrao:
            # Documento.clean() exige ficha OU nome digitado. Numa importação em
            # lote não há como saber de quem é cada arquivo, e inventar um nome
            # seria pior que não importar: viraria dado falso no acervo.
            return pular('sem "de quem é" — passe --nome-padrao')

        total['entram'] += 1
        total['bytes'] += tamanho
        placar['entram'] += 1
        placar['bytes'] += tamanho
        if not resumo:
            # Seta em ASCII, não "→": o console do Windows usa cp1252, que não
            # codifica U+2192, e o comando morria com UnicodeEncodeError no
            # primeiro arquivo — no meio de uma importação já começada.
            self.stdout.write(f'  entra   {relativo} -> "{titulo}" ({ano})')

        if seco:
            return

        with transaction.atomic():
            documento = Documento(
                colecao=colecao, titulo=titulo, ano=ano,
                nome_avulso=nome_padrao, enviado_por=enviado_por,
                descricao=f'Importado de {relativo.as_posix()}',
            )
            with arquivo.open('rb') as bruto:
                documento.arquivo.save(arquivo.name, File(bruto), save=False)
            documento.save()
