"""Importa a planilha "Parceiros Felizes" para o CRM.

Uso:
    python manage.py importar_parceiros "Parceiros Felizes - Arrecadacao 2026.csv" --ano 2026
    python manage.py importar_parceiros arquivo.csv --ano 2026 --lancar-no-financeiro

Por padrão as contribuições importadas NÃO viram lançamento no Financeiro —
o histórico costuma já ter sido lançado por outro caminho, e duplicar receita
é pior do que faltar. Use --lancar-no-financeiro se o histórico ainda não
estiver no Financeiro.

O arquivo exportado do Google Sheets costuma vir em UTF-8; se ele tiver sido
salvo/aberto como Latin-1, a acentuação chega corrompida ("Ã§" no lugar de "ç").
O comando detecta e conserta isso sozinho.
"""
import csv
import datetime
import re
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from parceiros.models import Contribuicao, Parceiro
from voluntario.models import Voluntario

MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
         'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']


def consertar_acentos(texto):
    """Repara texto UTF-8 que foi lido como Latin-1 ('Ã§' -> 'ç')."""
    if not texto or not any(marca in texto for marca in ('Ã', 'Â')):
        return texto
    try:
        return texto.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def valor_para_decimal(bruto):
    """'R$ 1.234,56' -> Decimal('1234.56'). Devolve None se não houver valor."""
    if not bruto:
        return None
    limpo = bruto.strip()
    if limpo in ('-', '', '—', 'R$', 'R$ -'):
        return None
    limpo = re.sub(r'[^\d,.-]', '', limpo)      # tira "R$" e espaços
    if not limpo or limpo == '-':
        return None
    limpo = limpo.replace('.', '').replace(',', '.')   # pt-BR -> decimal
    try:
        valor = Decimal(limpo)
    except InvalidOperation:
        return None
    return valor if valor > 0 else None


class Command(BaseCommand):
    help = 'Importa parceiros e contribuições da planilha de arrecadação (CSV).'

    def add_arguments(self, parser):
        parser.add_argument('csv', help='Caminho do arquivo CSV exportado da planilha.')
        parser.add_argument('--ano', type=int, required=True,
                            help='Ano de competência das colunas de mês.')
        parser.add_argument('--lancar-no-financeiro', action='store_true',
                            help='Também gera os lançamentos de receita (cuidado com duplicidade).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Só mostra o que faria, sem gravar nada.')

    def handle(self, *args, **opcoes):
        caminho, ano = opcoes['csv'], opcoes['ano']
        lancar, simular = opcoes['lancar_no_financeiro'], opcoes['dry_run']

        try:
            with open(caminho, encoding='utf-8-sig', newline='') as arquivo:
                linhas = list(csv.reader(arquivo))
        except FileNotFoundError:
            raise CommandError(f'Arquivo não encontrado: {caminho}')

        # Acha o cabeçalho: a linha que contém "Doador".
        indice_cab = next(
            (i for i, l in enumerate(linhas)
             if any('doador' in consertar_acentos(c).strip().lower() for c in l)),
            None)
        if indice_cab is None:
            raise CommandError('Não achei a linha de cabeçalho (nenhuma coluna "Doador").')

        cabecalho = [consertar_acentos(c).strip().lower() for c in linhas[indice_cab]]
        col_resp = next((i for i, c in enumerate(cabecalho) if 'respons' in c), None)
        col_doador = next((i for i, c in enumerate(cabecalho) if 'doador' in c), None)
        col_mes = {}
        for i, c in enumerate(cabecalho):
            for numero, nome in enumerate(MESES, start=1):
                if c == nome:
                    col_mes[numero] = i
        if col_doador is None or not col_mes:
            raise CommandError('Cabeçalho sem coluna de doador ou sem colunas de mês.')

        # Voluntários ativos, para casar o responsável pelo primeiro nome.
        voluntarios = list(Voluntario.objects.filter(data_saida__isnull=True))

        def achar_voluntario(nome):
            if not nome:
                return None
            alvo = nome.strip().lower()
            for v in voluntarios:
                candidatos = {
                    (v.first_name or '').strip().lower(),
                    (v.get_full_name() or '').strip().lower(),
                    (v.username or '').strip().lower(),
                    (getattr(v, 'apelido', '') or '').strip().lower(),
                }
                if alvo in candidatos - {''}:
                    return v
            return None

        criados = atualizados = contribuicoes = 0
        sem_responsavel = []

        with transaction.atomic():
            for linha in linhas[indice_cab + 1:]:
                if col_doador >= len(linha):
                    continue
                nome = consertar_acentos(linha[col_doador]).strip()
                if not nome:
                    continue
                # Ignora a linha de rodapé de totais.
                if 'arrecadado' in nome.lower():
                    continue

                nome_resp = consertar_acentos(linha[col_resp]).strip() if col_resp is not None and col_resp < len(linha) else ''
                responsavel = achar_voluntario(nome_resp)
                if nome_resp and responsavel is None:
                    sem_responsavel.append((nome, nome_resp))

                parceiro = Parceiro.objects.filter(nome__iexact=nome).first()
                if parceiro is None:
                    parceiro = Parceiro(nome=nome)
                    criados += 1
                else:
                    atualizados += 1
                parceiro.responsavel = responsavel or parceiro.responsavel
                if not simular:
                    parceiro.save()

                for numero_mes, indice in col_mes.items():
                    if indice >= len(linha):
                        continue
                    valor = valor_para_decimal(linha[indice])
                    if valor is None:
                        continue
                    competencia = datetime.date(ano, numero_mes, 1)
                    contribuicoes += 1
                    if simular:
                        continue
                    if Contribuicao.objects.filter(parceiro=parceiro, competencia=competencia).exists():
                        continue
                    contribuicao = Contribuicao(
                        parceiro=parceiro, competencia=competencia, valor=valor,
                        data_recebimento=competencia, forma='',
                        observacao='Importado da planilha',
                    )
                    if not lancar:
                        contribuicao.pular_lancamento = True   # lido pelo sinal
                    contribuicao.save()

            if simular:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f'{"[simulação] " if simular else ""}'
            f'{criados} parceiro(s) criado(s), {atualizados} atualizado(s), '
            f'{contribuicoes} contribuição(ões) de {ano}.'))
        if lancar:
            self.stdout.write(self.style.WARNING(
                'Lançamentos de receita foram gerados no Financeiro.'))
        else:
            self.stdout.write(
                'Nenhum lançamento no Financeiro (use --lancar-no-financeiro se precisar).')
        if sem_responsavel:
            self.stdout.write(self.style.WARNING(
                '\nResponsáveis não encontrados entre os voluntários ativos '
                '(o parceiro ficou sem responsável — ajuste pela tela):'))
            for parceiro_nome, resp in sem_responsavel:
                self.stdout.write(f'  - {parceiro_nome}: "{resp}"')
