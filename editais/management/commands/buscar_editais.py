"""Varredura diária das fontes de editais.

Lê as fontes JÁ CADASTRADAS. Para descobrir edital em site que ninguém
mapeou, o comando é o `varrer_editais`, que pergunta a um buscador.

Uso:
    python manage.py buscar_editais
    python manage.py buscar_editais --fonte abcr --minimo 3
    python manage.py buscar_editais --dry-run

Feito para rodar em tarefa agendada no PythonAnywhere. Duas regras mandam aqui:

1. Uma fonte quebrada não derruba as outras (quem engole o erro é
   `coleta.coletar_fonte`, que devolve lista vazia e grava o motivo na fonte).
2. Edital que já existe não é sobrescrito. Status, requisitos, observações e
   responsável são trabalho humano — o robô só recalcula a nota que ele mesmo
   deu, porque as palavras-chave podem ter mudado desde a última varredura.
"""
from django.core.management.base import BaseCommand

from editais import coleta
from editais.models import FonteEdital, PalavraChave


class Command(BaseCommand):
    help = 'Varre as fontes cadastradas e guarda os editais relevantes ao PCF.'

    def add_arguments(self, parser):
        parser.add_argument('--fonte', default='',
                            help='Roda só nas fontes cujo nome contém este texto.')
        parser.add_argument('--minimo', type=int, default=2,
                            help='Nota mínima de relevância para guardar o edital (padrão: 2).')
        parser.add_argument('--dry-run', action='store_true',
                            help='Só mostra o que faria, sem gravar edital nenhum.')

    def handle(self, *args, **opcoes):
        nome_fonte, minimo, simular = opcoes['fonte'], opcoes['minimo'], opcoes['dry_run']

        fontes = FonteEdital.objects.filter(ativo=True)
        if nome_fonte:
            fontes = fontes.filter(nome__icontains=nome_fonte)
        fontes = list(fontes)
        if not fontes:
            self.stdout.write(self.style.WARNING(
                'Nenhuma fonte ativa para varrer. Cadastre e ative em /editais/fontes/.'))
            return

        # Carrega o dicionário uma vez só: são poucas palavras e o laço roda
        # por item de cada fonte.
        palavras = list(PalavraChave.objects.filter(ativo=True))
        if not palavras:
            self.stdout.write(self.style.WARNING(
                'Nenhuma palavra-chave ativa: sem elas tudo tira nota zero. '
                'Rode "python manage.py seed_editais" ou cadastre em /editais/palavras/.'))

        lidos = novos = ignorados = com_erro = 0

        for fonte in fontes:
            itens = coleta.coletar_fonte(fonte)
            novos_da_fonte = ignorados_da_fonte = 0

            for item in itens:
                # A regra de pontuar/gravar mora em coleta.registrar_item, para
                # ser exatamente a mesma da varredura na web (varrer_editais).
                resultado, _ = coleta.registrar_item(
                    item, palavras, minimo, fonte=fonte, origem='ROBO', simular=simular)
                if resultado == 'ignorado':
                    ignorados_da_fonte += 1
                elif resultado == 'novo':
                    novos_da_fonte += 1

            lidos += len(itens)
            novos += novos_da_fonte
            ignorados += ignorados_da_fonte

            if fonte.ultimo_erro:
                com_erro += 1
                self.stdout.write(self.style.ERROR(
                    f'  {fonte.nome}: falhou — {fonte.ultimo_erro}'))
            else:
                linha = (f'  {fonte.nome}: {len(itens)} lido(s), '
                         f'{novos_da_fonte} novo(s), {ignorados_da_fonte} fora do perfil')
                self.stdout.write(self.style.SUCCESS(linha) if novos_da_fonte else linha)

        resumo = (f'{"[simulação] " if simular else ""}'
                  f'{len(fontes)} fonte(s), {lidos} item(ns) lido(s), '
                  f'{novos} edital(is) novo(s), {ignorados} abaixo da nota {minimo}.')
        self.stdout.write(self.style.SUCCESS(resumo) if novos else resumo)
        if com_erro:
            self.stdout.write(self.style.WARNING(
                f'{com_erro} fonte(s) com erro — confira em /editais/fontes/.'))
